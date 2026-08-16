import re
import base64
from pathlib import Path
from difflib import get_close_matches
from typing import Any, Dict, List, Tuple, Optional
from utility import (
  run_remote_command,
  run_command,
)
from config import (
    ANSIBLE_CONTROL_NODE,
    REMOTE_PROJECT_ROOT,
    SAFE_ROOT,
)

# =========================================================
# Validation
# =========================================================

def validate_base64(data: str) -> bool:
    if not data:
        return False
    data = data.strip()
    if not re.match(r"^[A-Za-z0-9+/=\r\n]+$", data):
        return False
    try:
        base64.b64decode(data, validate=True)
        return True
    except Exception:
        return False


def semantic_yaml_check(obj: Any) -> List[str]:
    problems: List[str] = []
    known_yaml_keys = {
        "pod_name",
        "mysql_container_name",
        "web_container_name",
        "mysql_root_password",
        "mysql_image",
        "web_image",
        "html_dir",
        "web_port",
        "mysql_db",
    }

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                matches = get_close_matches(k, known_yaml_keys, n=1, cutoff=0.80)
                if matches and k != matches[0]:
                    problems.append(f"Possible typo: {k} -> {matches[0]}")
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return problems


def validate_known_paths(text: str) -> List[str]:
    problems = []
    known_paths = [
        "/home/vboxuser/containers/html",
        "/home/vboxuser/containers/html/index.php",
        "/home/vboxuser/containers/mysql",
    ]
    path_pattern = r"/home/[^\s\"']+"
    paths = re.findall(path_pattern, text)

    for p in paths:
        match = get_close_matches(p, known_paths, n=1, cutoff=0.85)
        if match and p != match[0]:
            problems.append(f"Possible path typo: {p} -> {match[0]}")

    return problems


def validate_cross_file_consistency(playbook_file: Path, php_file: Path) -> List[dict]:
    errors: List[dict] = []
    if not playbook_file.exists() or not php_file.exists():
        return errors

    playbook_text = playbook_file.read_text(encoding="utf-8")
    php_text = php_file.read_text(encoding="utf-8")

    mysql_db = re.search(r"MYSQL_DATABASE=(\w+)", playbook_text)
    php_db = re.search(r'\$db\s*=\s*"([^"]+)"', php_text)

    if mysql_db and php_db and mysql_db.group(1) != php_db.group(1):
        errors.append({"type": "cross_file", "playbook_db": mysql_db.group(1), "php_db": php_db.group(1)})

    return errors


def validate_podman_playbook(playbook_file: Path) -> List[dict]:
    errors: List[dict] = []

    try:
        import yaml

        playbook_text = playbook_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(playbook_text)

        if not isinstance(parsed, list):
            errors.append({
                "type": "invalid_playbook_structure",
                "file": str(playbook_file),
                "stderr": "Playbook root must be a YAML list."
            })
            return errors

        for play in parsed:
            if not isinstance(play, dict):
                continue

            if "tasks" not in play:
                errors.append({
                    "type": "missing_tasks",
                    "file": str(playbook_file),
                    "stderr": "Ansible play requires tasks."
                })

            # taskがplaybook rootに直接置かれているケースを検出
            if (
                "tasks" not in play
                and any(
                    key.startswith("containers.podman.")
                    for key in play.keys()
                )
            ):
                errors.append({
                    "type": "task_list_without_play",
                    "file": str(playbook_file),
                    "stderr": "Podman task found at playbook root. Add hosts and tasks."
                })

            if "hosts" not in play:
                errors.append({
                    "type": "missing_hosts",
                    "file": str(playbook_file),
                    "stderr": "Ansible play requires hosts."
                })

    except Exception as e:
        return [{"type": "yaml_parse", "file": str(playbook_file), "stderr": str(e)}]

    container_port_usage = False
    pod_publish_defined = False

    def walk(node: Any) -> None:
        nonlocal container_port_usage, pod_publish_defined

        if isinstance(node, dict):
            if "containers.podman.podman_container" in node:
                container_config = node["containers.podman.podman_container"]
                if isinstance(container_config, dict):
                    if "ports" in container_config:
                        container_port_usage = True
                        errors.append({
                            "type": "podman_container_ports",
                            "file": str(playbook_file),
                            "stderr": "Do not define ports on podman_container when using a shared pod.",
                        })
                    if "environment" in container_config:
                        errors.append({
                            "type": "podman_environment_key",
                            "file": str(playbook_file),
                            "stderr": "Use env instead of environment for podman_container.",
                        })
            if "containers.podman.podman_pod" in node:
                pod_config = node["containers.podman.podman_pod"]
                if isinstance(pod_config, dict) and "publish" in pod_config:
                    pod_publish_defined = True
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parsed)

    if container_port_usage and not pod_publish_defined:
        errors.append({
            "type": "pod_publish_missing",
            "file": str(playbook_file),
            "stderr": "Define podman_pod.publish when exposing ports.",
        })

    return errors


def run_validation(safe_root: Path, inventory_file: Path, playbook_file: Path, php_file: Path) -> Tuple[List[dict], str, str]:
    validation_errors: List[dict] = []
    import yaml

    try:
        if not playbook_file.exists():
            validation_errors.append({"type": "missing_playbook", "file": str(playbook_file)})
        else:
            parsed = yaml.safe_load(playbook_file.read_text(encoding="utf-8"))
            if not isinstance(parsed, list):
                validation_errors.append({"type": "invalid_playbook", "file": str(playbook_file), "stderr": "Playbook must be a YAML list."})
    except Exception as e:
        validation_errors.append({"type": "yaml_parse", "file": str(playbook_file), "stderr": str(e)})

    validation_errors.extend(validate_podman_playbook(playbook_file))
    validation_errors.extend(validate_cross_file_consistency(playbook_file, php_file))

    stdout = ""
    stderr = ""

# remote validation temporarily disabled
    # if inventory_file.exists() and playbook_file.exists():
    #     remote_cmd = f"cd {REMOTE_PROJECT_ROOT} && ansible-playbook -i ansible/inventory.ini ansible/playbook.yml --check"
    #     code, stdout, stderr = run_remote_command(ANSIBLE_CONTROL_NODE, remote_cmd)
    #     if code != 0:
    #         validation_errors.append({"type": "ansible_syntax", "file": str(playbook_file), "stdout": stdout, "stderr": stderr})

    print("RETURN ERROR COUNT =", len(validation_errors))
    return validation_errors, stdout, stderr

def run_remote_validation() -> Tuple[List[dict], str, str]:
    """
    Ansible Control Node上の成果物を検証する。
    """

    print("======= REMOTE VALIDATION =======")

    source = str(SAFE_ROOT) + "/."
    
    code, stdout, stderr = run_command([
        "scp",
        "-r",
        source,
        f"{ANSIBLE_CONTROL_NODE}:{REMOTE_PROJECT_ROOT}"
    ])

    if code != 0:
        raise RuntimeError(stderr)

    remote_cmd = (
        f"cd {REMOTE_PROJECT_ROOT} && "
        "ansible-playbook "
        "--syntax-check "
        "-i ansible/inventory.ini "
        "ansible/playbook.yml"
    )

    code, stdout, stderr = run_remote_command(
        ANSIBLE_CONTROL_NODE,
        remote_cmd
    )

    code2, stdout2, stderr2 = run_remote_command(
        ANSIBLE_CONTROL_NODE,
        f"head -30 {REMOTE_PROJECT_ROOT}/ansible/playbook.yml"
    )

    print(stdout2)

    errors = []

    if code != 0:
        errors.append(
            {
                "type": "ansible_syntax",
                "stderr": stderr,
            }
        )

    return errors, stdout or "", stderr or ""