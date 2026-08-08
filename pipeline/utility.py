import re
import json
import subprocess
import base64
import binascii

from pathlib import Path

from typing import (
    Any,
    Dict,
    List,
    Tuple,
    Optional,
)

from json_repair import repair_json

from config import (
    PROJECT_ROOT,
    CATEGORY_TO_TARGET,
)

# =========================================================
# Utility
# =========================================================

def extract_json(text: Optional[str]) -> str:
    """AIレスポンスから JSON 部分のみ抽出して返す。"""

    text = (text or "").strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    obj_start = text.find("{")
    arr_start = text.find("[")

    candidates = [x for x in (obj_start, arr_start) if x != -1]
    if not candidates:
        raise ValueError("JSON start not found")

    start = min(candidates)
    end = text.rfind("}") if text[start] == "{" else text.rfind("]")

    if end == -1:
        raise ValueError("Incomplete JSON response")

    return text[start:end + 1]


def sanitize_json_string(text: str) -> str:
    """JSON の不正なバックスラッシュをエスケープして返す。"""

    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)


def safe_json_loads(text: str) -> Dict[str, Any]:
    """壊れた JSON を修復して dict を返す。修復できなければ例外を投げる。"""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = sanitize_json_string(repair_json(text))
        print("\n=== REPAIRED JSON ===")
        print(repaired[:1500])
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
            (PROJECT_ROOT / "logs/broken_json.txt").write_text(repaired, encoding="utf-8")
            raise RuntimeError(f"JSON repair failed: {e}")


def encode_b64(content: str) -> str:
    """UTF-8 でエンコードした文字列を base64 文字列で返す。"""

    return base64.b64encode(content.encode("utf-8")).decode("utf-8")


def decode_b64(content: str) -> str:
    """base64 文字列をデコードして UTF-8 文字列で返す。"""

    content = content.strip().replace("\n", "").replace("\r", "")
    missing_padding = len(content) % 4
    if missing_padding:
        content += "=" * (4 - missing_padding)
    try:
        raw = base64.b64decode(content, validate=False)
        return raw.decode("utf-8", errors="replace")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid base64 content: {e}")


def safe_write_file(root: Path, relative_path: str, content: str) -> None:
    """Path-traversal を防いでファイルを書き込む。"""

    resolved = (root / relative_path).resolve()
    print(f"safe_write_file root={root} relative_path={relative_path} resolved={resolved}")
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"Path traversal detected: {relative_path}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    print(f"Generated: {resolved}")


def log_text(path: Path, text: str) -> None:
    """指定パスへテキストログを書き込む（ディレクトリを自動作成）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(command: List[str]) -> Tuple[int, str, str]:
    """外部コマンドを実行して (returncode, stdout, stderr) を返す。"""

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as e:
        return 999, "", str(e)


def run_remote_command(host: str, remote_command: str) -> Tuple[int, str, str]:
    """SSH 経由でリモートコマンドを実行するラッパー。"""

    return run_command(["ssh", "-o", "BatchMode=yes", host, remote_command])


def repair_yaml_text(text: str) -> str:
    """軽微な YAML 破損を修復する。"""

    text = re.sub(r"\{\{\s*([^\}]+)\s*\}\}", r"{{ \1 }}", text)
    text = re.sub(r"([^\n])(\s+[A-Za-z_][A-Za-z0-9_]*:)", r"\1\n\2", text)
    text = re.sub(r"(- name:[^\n]+)\s+([a-zA-Z0-9_.]+:)", r"\1\n  \2", text)
    text = re.sub(r"([^\n])(group:)", r"\1\n\2", text)
    text = re.sub(r'"{{\s*([^}]+)\s*}}([^"\n]*)', r'"{{ \1 }}\2"', text)
    return text


def strip_markdown_fence(text: Optional[str]) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def repair_podman_yaml_content(content: str) -> str:
    """Podman/Ansible の生成誤りを自動修復する。"""

    try:
        import yaml

        parsed = yaml.safe_load(content)
    except Exception:
        return content

    if not isinstance(parsed, (list, dict)):
        return content

    pod_publish_ports: List[str] = []
    pod_configs: List[dict] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key == "containers.podman.podman_container" and isinstance(value, dict):
                    publish_values = []
                    for field_name in ("ports", ):
                        field_value = value.pop(field_name, None)
                        if field_value:
                            if isinstance(field_value, list):
                                for item in field_value:
                                    if isinstance(item, str):
                                        publish_values.append(item)
                                    elif isinstance(item, dict):
                                        for inner_key, inner_value in item.items():
                                            if isinstance(inner_value, str):
                                                publish_values.append(f"{inner_key}:{inner_value}")
                            elif isinstance(field_value, str):
                                publish_values.append(field_value)

                    if publish_values:
                        pod_publish_ports.extend(publish_values)

                    if "environment" in value and "env" not in value:
                        value["env"] = value.pop("environment")

                    env_value = value.get("env")
                    if isinstance(env_value, list):
                        normalized_env = {}
                        for item in env_value:
                            if isinstance(item, str):
                                if "=" in item:
                                    key, env_value_part = item.split("=", 1)
                                    normalized_env[key] = env_value_part
                                else:
                                    normalized_env[item] = ""
                            elif isinstance(item, dict):
                                for env_key, env_val in item.items():
                                    if isinstance(env_key, str) and isinstance(env_val, str):
                                        normalized_env[env_key] = env_val
                        if normalized_env:
                            value["env"] = normalized_env

                elif key == "containers.podman.podman_pod" and isinstance(value, dict):
                    pod_configs.append(value)

                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(parsed)

    print("DEBUG parsed type =", type(parsed))
    print("DEBUG parsed head =", parsed[:1] if isinstance(parsed, list) else parsed)

    for pod_config in pod_configs:
        if pod_publish_ports:
            existing_publish = pod_config.get("publish") or []
            if isinstance(existing_publish, list):
                merged_publish = list(existing_publish)
            else:
                merged_publish = [existing_publish]
            for port in pod_publish_ports:
                if port not in merged_publish:
                    merged_publish.append(port)
            pod_config["publish"] = merged_publish

    fixed_yaml = yaml.safe_dump(
        parsed,
        sort_keys=False,
        default_flow_style=False,
    )

    if isinstance(parsed, list) and not fixed_yaml.lstrip().startswith("-"):
        fixed_yaml = "- " + fixed_yaml

    return fixed_yaml

def plan_repair(
    diagnosis,
    browser_result,
    browser_issues,
    lint_result,
    lint_issues,
    deploy_result,
    deploy_diagnosis,
):
    # Reviewer診断を優先
    category = diagnosis.get("category")

    target = CATEGORY_TO_TARGET.get(category)

    if target is not None:
        return target

    # AIが判断できなかった場合だけPythonが補完
    if browser_issues:
        return "ansible/playbook.yml"

    if lint_issues:
        return "src/index.php"

    return None
