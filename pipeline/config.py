import os
from pathlib import Path
from typing import List

# =========================================================
# Constants
# =========================================================

BLOCKING_SEVERITIES: List[str] = ["BLOCKER"]

MAX_RETRY: int = 1
MAX_VALIDATION_RETRY: int = 2

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
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