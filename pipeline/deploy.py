from typing import Any, Dict, List, Tuple, Optional
from config import DEPLOY_ERROR_PATTERNS

from utility import (
    run_command,
    run_remote_command,
)
from config import (
    ANSIBLE_CONTROL_NODE,
    EXECUTION_NODE,
    REMOTE_PROJECT_ROOT,
)

# =========================================================
# Deploy
# =========================================================

def deploy_pipeline() -> Dict[str, Any]:
    print()
    print("===== DEPLOY =====")

    remote_cmd = (
        f"cd {REMOTE_PROJECT_ROOT} && "
        "ansible-playbook "
        "-i ansible/inventory.ini "
        "ansible/playbook.yml"
    )

    code, stdout, stderr = run_remote_command(ANSIBLE_CONTROL_NODE, remote_cmd)
    stdout = stdout or ""
    stderr = stderr or ""
    
    print(stdout)
    if stderr:
        print(stderr)
    print("Return code =", code)

    return {"success": code == 0, "stdout": stdout, "stderr": stderr}

# =========================================================
# Deploy Error Analysis
# =========================================================

def analyze_deploy_error(
    result: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deploy結果+解析証跡を解析し、Repair Planner向けの診断情報を返す。

    Parameters
    ----------
    result:
        deploy_pipeline() の戻り値

    Returns
    -------
    dict
        {
            "category": "...",
            "root_cause": "...",
            "reason": "...",
            "confidence": 0.99,
            "repair_hint": "..."
        }
    """

    # -------------------------
    # 成功でも実機確認する
    # -------------------------

    ps_output = evidence.get(
        "podman_ps_pod",
        {}
    ).get(
        "stdout",
        ""
    )

    pod_output = evidence.get(
        "podman_pod_ps",
        {}
    ).get(
        "stdout",
        ""
    )
    # -------------------------
    # phpコンテナ存在チェック
    # -------------------------

    if "php" not in ps_output:

        return {
            "category": "container",
            "root_cause": "php_container_missing",
            "reason": (
                "lamp-pod exists but php container "
                "was not created."
            ),
            "confidence": 0.95,
            "repair_hint": (
                "Review podman_container task "
                "for php in ansible/playbook.yml."
            ),
            "repair_target": "ansible/playbook.yml",
        }

    # -------------------------
    # mysql存在チェック
    # -------------------------

    if "mysql" not in ps_output:

        return {
            "category": "database",
            "root_cause": "mysql_container_missing",
            "reason": (
                "mysql container was not created."
            ),
            "confidence": 0.95,
            "repair_hint": (
                "Review mysql podman_container task."
            ),
            "repair_target": "ansible/playbook.yml",
        }

    # -------------------------
    # curl失敗
    # -------------------------

    curl_stderr = evidence.get(
        "curl",
        {}
    ).get(
        "stderr",
        ""
    )

    if curl_stderr:

        return {
            "category": "network",
            "root_cause": "browser_connection_error",
            "reason": curl_stderr,
            "confidence": 0.8,
            "repair_hint": (
                "Check apache container, "
                "pod publish and volume mount."
            ),
            "repair_target": "ansible/playbook.yml",
        }

    # -------------------------
    # 既存ロジック
    # -------------------------

    stderr = (
        result.get("stderr") or ""
    ).lower()


    if (
        "rootlessport cannot expose privileged port 80"
        in stderr
    ):
        return {
            "category": "environment",
            "root_cause": "rootless_privileged_port",
            "reason": (
                "Rootless Podman cannot bind privileged port 80."
            ),
            "confidence": 0.99,
            "repair_hint": (
                "Use port >=1024."
            ),
            "repair_target": "ansible/playbook.yml",
        }


    for pattern, diagnosis in DEPLOY_ERROR_PATTERNS.items():

        if pattern.lower() in stderr:
            return diagnosis.copy()

    return {
        "category": "deployment",
        "root_cause": "unknown",
        "reason": stderr,
        "confidence": 0.3,
        "repair_hint": "Review deployment log.",
        "repair_target": "ansible/playbook.yml",
    }

def run_browser_validation() -> Dict[str, Any]:
    """デプロイ後のブラウザ検証を実行する。"""

    url = "http://192.168.122.10:8080"
    code, stdout, stderr = run_command(["curl", "-sS", "-D", "-", url])
    stdout = stdout or ""
    stderr = stderr or ""

    headers_text = stdout
    body_text = ""
    for separator in ("\r\n\r\n", "\n\n"):
        if separator in stdout:
            headers_text, body_text = stdout.split(separator, 1)
            break

    header_lines = [line for line in headers_text.splitlines() if line]
    status_line = header_lines[0] if header_lines else ""
    status_code = 200
    if status_line.startswith("HTTP/"):
        status_code = int(status_line.split()[1])

    headers: Dict[str, str] = {}
    for line in header_lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()

    return {
        "success": code == 0,
        "status": status_code,
        "body": body_text,
        "headers": headers,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_php_lint() -> Dict[str, Any]:
    """対象 PHP ファイルの構文チェックを実行する。"""

    remote_cmds = [
        "php -l /var/www/html/index.php",
        "podman run --rm -v /home/vboxuser/containers/html:/var/www/html php:8.2-apache php -l /var/www/html/index.php",
    ]

    for remote_cmd in remote_cmds:
        code, stdout, stderr = run_remote_command(EXECUTION_NODE, remote_cmd)
        if code == 0:
            return {"success": True, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}
        if "command not found" not in (stderr or "").lower() and "not found" not in (stderr or "").lower():
            return {"success": False, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}

    return {"success": False, "exit_code": 127, "stdout": "", "stderr": "php command not found"}


def collect_deploy_evidence():

    evidence = {}

    commands = {
        "podman_ps":
            "podman ps -a",

        "podman_ps_pod":
            "podman ps -a --pod",

        "podman_pod_ps":
            "podman pod ps",

        "php_logs":
            "podman logs php",

        "mysql_logs":
            "podman logs mysql",

        "pod_inspect":
            "podman inspect lamp-pod",

        "curl":
            "curl -i http://localhost:8080"
    }

    for key, cmd in commands.items():

        code, stdout, stderr = run_remote_command(
            EXECUTION_NODE,
            cmd
        )

        print(
            f"\n=== EXECUTION_NODE {key} ==="
        )

        print(stdout)

        if stderr:
            print(stderr)

        evidence[key] = {
            "returncode": code,
            "stdout": stdout,
            "stderr": stderr,
        }

    code, stdout, stderr = run_remote_command(
        EXECUTION_NODE,
        "ls -l /home/vboxuser/containers/html"
    )

    print("\n=== HOST HTML ===")
    print(stdout)

    evidence["host_html"]={
        "returncode":code,
        "stdout":stdout,
        "stderr":stderr,
    }

    code, stdout, stderr = run_remote_command(
        EXECUTION_NODE,
        "podman exec php sh -c 'head -20 /var/www/html/index.php'"
    )

    print("\n=== CONTAINER index.php ===")
    print(stdout)

    evidence["container_php"]={
        "returncode":code,
        "stdout":stdout,
        "stderr":stderr,
    }

    return evidence

def analyze_deploy_result(result: dict, evidence: dict) -> dict:
    """
    Deploy後の各種ログから原因を診断する。

    Parameters
    ----------
    result : dict
        deploy_pipeline() の戻り値
    evidence : dict
        collect_deploy_evidence() の戻り値

    Returns
    -------
    dict
    """

    diagnosis = {
        "category": "deployment",
        "root_cause": "unknown",
        "reason": "",
        "confidence": 0.3,
        "repair_target": "ansible/playbook.yml",
        "evidence": evidence
    }

    # -------------------------------
    # Deploy自体が失敗
    # -------------------------------

    if not result.get("success", False):

        stderr = result.get("stderr", "")

        if "rootlessport" in stderr:
            diagnosis.update({
                "root_cause": "pod_publish_error",
                "reason": "Rootless Podman cannot expose privileged ports.",
                "confidence": 0.99,
                "repair_target": "ansible/playbook.yml",
                "evidence": evidence
            })
            return diagnosis

        if "permission denied" in stderr:
            diagnosis.update({
                "root_cause": "permission_error",
                "reason": stderr,
                "confidence": 0.95,
                "repair_target": "ansible/playbook.yml",
                "evidence": evidence
            })
            return diagnosis

    # -------------------------------
    # 各種ログ
    # -------------------------------

    podman_ps = evidence.get("podman_ps", {}).get("stdout", "")
    podman_pod_ps = evidence.get("podman_pod_ps", {}).get("stdout", "")
    php_logs = evidence.get("php_logs", {}).get("stdout", "")
    mysql_logs = evidence.get("mysql_logs", {}).get("stdout", "")
    pod_inspect = evidence.get("pod_inspect", {}).get("stdout", "")

    curl_stdout = evidence.get("curl", {}).get("stdout", "")
    curl_stderr = evidence.get("curl", {}).get("stderr", "")

    # -------------------------------
    # phpコンテナが無い
    # -------------------------------

    if "php" not in podman_ps:

        diagnosis.update({
            "root_cause": "container_not_running",
            "reason": "PHP container does not exist.",
            "confidence": 0.99,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # mysqlコンテナが無い
    # -------------------------------

    if "mysql" not in podman_ps:

        diagnosis.update({
            "root_cause": "mysql_not_running",
            "reason": "MySQL container does not exist.",
            "confidence": 0.99,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # Podが落ちている
    # -------------------------------

    if "Exited" in pod_inspect:

        diagnosis.update({
            "root_cause": "container_crashed",
            "reason": "Container exited immediately.",
            "confidence": 0.95,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # Apache起動失敗
    # -------------------------------

    if "Recv failure" in curl_stderr:

        diagnosis.update({
            "root_cause": "apache_not_started",
            "reason": curl_stderr.strip(),
            "confidence": 0.90,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # HTTPエラー
    # -------------------------------

    if "404" in curl_stdout:

        diagnosis.update({
            "root_cause": "php_file_missing",
            "reason": "index.php not found.",
            "confidence": 0.90,
            "repair_target": "src/index.php",
            "evidence": evidence
        })

        return diagnosis

    if "500" in curl_stdout:

        diagnosis.update({
            "root_cause": "php_runtime_error",
            "reason": "PHP Internal Server Error.",
            "confidence": 0.90,
            "repair_target": "src/index.php",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # MySQL接続失敗
    # -------------------------------

    mysql_text = mysql_logs.lower()

    if "access denied" in mysql_text:

        diagnosis.update({
            "root_cause": "mysql_auth_failed",
            "reason": mysql_logs.strip(),
            "confidence": 0.98,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    if "can't connect" in mysql_text:

        diagnosis.update({
            "root_cause": "mysql_connection_failed",
            "reason": mysql_logs.strip(),
            "confidence": 0.95,
            "repair_target": "ansible/playbook.yml",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # phpログ
    # -------------------------------

    php_text = php_logs.lower()

    if "fatal error" in php_text:

        diagnosis.update({
            "root_cause": "php_fatal_error",
            "reason": php_logs.strip(),
            "confidence": 0.98,
            "repair_target": "src/index.php",
            "evidence": evidence
        })

        return diagnosis

    # -------------------------------
    # 正常
    # -------------------------------

    if result.get("success"):

        diagnosis.update({
            "root_cause": "success",
            "reason": "Deploy and runtime checks look healthy.",
            "confidence": 1.0,
        })

    return diagnosis