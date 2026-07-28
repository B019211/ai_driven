from typing import Any, Dict, List, Tuple, Optional

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