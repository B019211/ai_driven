import os
from pathlib import Path
from typing import List

# =========================================================
# Constants
# =========================================================

BLOCKING_SEVERITIES: List[str] = ["BLOCKER"]

MAX_RETRY: int = 1
MAX_VALIDATION_RETRY: int = 2
MAX_DEPLOY_RETRY: int = 3

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
TASK_DIR = Path("tasks")
SAFE_ROOT: Path = (PROJECT_ROOT / "generated/files").resolve()

MODEL_NAME: str = "qwen3:8b"
PIPELINE_PHASE: str = "learning"

ANSIBLE_CONTROL_NODE: str = "asbsvr"
EXECUTION_NODE: str = "rockey8"

REMOTE_PROJECT_ROOT: str = "/home/vboxuser/ai_driven/generated/files"

ALLOWED_PATHS = {
    "ansible/playbook.yml",
    "ansible/inventory.ini",
    "src/index.php",
}

CATEGORY_TO_TARGET = {
    "application": "src/index.php",
    "deployment": "ansible/playbook.yml",
    "configuration": "ansible/inventory.ini",
    "infrastructure": "Dockerfile"
}

DEPLOY_ERROR_PATTERNS = {
    "rootlessport cannot expose privileged port": {
        "category": "deployment",
        "root_cause": "privileged_port",
        "reason": "Rootless Podman cannot bind host port 80.",
        "repair_hint": "Use host port >=1024."
    }
}

TASK_SEQUENCE = [
    "infrastructure.md",
    "application.md",
]