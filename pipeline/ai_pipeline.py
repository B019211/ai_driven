from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from openai import OpenAI

from json_repair import repair_json
from jsonschema import validate
from jsonschema import ValidationError

import base64
import json
import os
import re
import time
import binascii
import subprocess


# =========================================================
# Constants
# =========================================================

BLOCKING_SEVERITIES = ["BLOCKER"]

MAX_RETRY = 1

SAFE_ROOT = Path("generated/files").resolve()

MODEL_NAME = "qwen3:8b"
PIPELINE_PHASE = "learning"

ANSIBLE_CONTROL_NODE = "asbsvr"
EXECUTION_NODE = "rockey8"

REMOTE_PROJECT_ROOT = "/home/vboxuser/ai_driven/generated/files"

ALLOWED_PATHS = {
    "ansible/playbook.yml",
    "ansible/inventory.ini",
    "src/index.php"
}

# =========================================================
# Utility
# =========================================================

def extract_json(text: str) -> str:
    """
    AIレスポンスからJSON部分のみ抽出
    """

    text = text.strip()

    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    text = text.strip()

    obj_start = text.find("{")
    arr_start = text.find("[")

    candidates = [
        x for x in [obj_start, arr_start]
        if x != -1
    ]

    if not candidates:
        raise ValueError("JSON start not found")

    start = min(candidates)

    if text[start] == "{":
        end = text.rfind("}")
    else:
        end = text.rfind("]")

    # JSON終端が見つからない場合は
    # 途中までをrepair_jsonへ渡す
    if end == -1:
        return text[start:]

    return text[start:end + 1]


def sanitize_json_string(text: str) -> str:
    """
    JSONとして不正なバックスラッシュを修正
    """

    text = re.sub(
        r'\\(?!["\\/bfnrtu])',
        r'\\\\',
        text
    )

    return text


def safe_json_loads(text: str) -> dict:
    """
    壊れたJSONを安全に読み込む
    """

    try:
        return json.loads(text)

    except json.JSONDecodeError:

        repaired = repair_json(text)

        repaired = sanitize_json_string(
            repaired
        )

        print("\n=== REPAIRED JSON ===")
        print(repaired[:1500])

        try:
            return json.loads(repaired)

        except json.JSONDecodeError as e:

            Path("logs").mkdir(exist_ok=True)

            Path("logs/broken_json.txt").write_text(
                repaired,
                encoding="utf-8"
            )

            raise RuntimeError(
                f"JSON repair failed: {e}"
            )

def encode_b64(content: str) -> str:
    return base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")


def decode_b64(content: str) -> str:

    content = content.strip()

    # 改行除去
    content = content.replace("\n", "")
    content = content.replace("\r", "")

    # padding補正
    missing_padding = len(content) % 4

    if missing_padding:
        content += "=" * (4 - missing_padding)

    try:

        raw = base64.b64decode(
            content,
            validate=False
        )

        return raw.decode(
            "utf-8",
            errors="replace"
        )

    except (
        binascii.Error,
        UnicodeDecodeError
    ) as e:

        raise ValueError(
            f"Invalid base64 content: {e}"
        )


def safe_write_file(
    root: Path,
    relative_path: str,
    content: str
):
    """
    path traversal防御付きファイル保存
    """

    resolved = (
        root / relative_path
    ).resolve()

    if not str(resolved).startswith(
        str(root.resolve())
    ):
        raise ValueError(
            f"Path traversal detected: {relative_path}"
        )

    resolved.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    resolved.write_text(
        content,
        encoding="utf-8"
    )

    print(f"Generated: {resolved}")


def log_text(path: Path, text: str):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        text,
        encoding="utf-8"
    )

def run_command(command: list[str]) -> tuple[int, str, str]:
    """
    コマンド実行
    """

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding = "utf-8",
            errors = "replace",
            timeout=120
        )

        return (
            result.returncode,
            result.stdout or "",
            result.stderr or ""
        )

    except Exception as e:

        return (
            999,
            "",
            str(e)
        )

def run_remote_command(
host: str,
remote_command: str
) -> tuple[int, str, str]:
    """
    SSH経由でリモート実行
    """

    return run_command([
        "ssh",
        "-o",
        "BatchMode=yes",
        host,
        remote_command
    ])

def regenerate_file(
    path: str
) -> str:
    """
    単一ファイル再生成
    """

    prompt = f"""
以下ファイルのみ生成してください。

path:
{path}

重要:
- ファイル内容のみ返却
- markdown禁止
- explanation禁止
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": Path(
                    "prompts/php_engineer.txt"
                ).read_text(
                    encoding="utf-8"
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0,
        max_tokens=8192
    )

    text = response.choices[0].message.content

    if not text:
        raise RuntimeError(f"Empty response for {path}")

    return strip_markdown_fence(text).strip()

def regenerate_file_with_context(
    path: str,
    architecture: str,
    context_data
) -> str:

    print("=== REGENERATE START ===")
    print(path)

    current_file = (
        SAFE_ROOT / path
    ).read_text(
        encoding="utf-8"
    )

    validation_log = "\n".join(
        err.get("stdout", "") + "\n" + err.get("stderr", "")
        for err in context_data["errors"]
    )

    # AIに分かりやすい修正指示を生成
    error_summary = []

    for err in context_data["errors"]:

        text = (
            err.get("stdout", "")
            + "\n"
            + err.get("stderr", "")
        )

        if "Unsupported parameters" in text:
            error_summary.append(
                "- Remove unsupported parameters."
            )

        if "timeout" in text:
            error_summary.append(
                "- Delete timeout parameter."
            )

    error_summary = "\n".join(error_summary)


    prompt = f"""
# Validation Errors

{json.dumps(context_data["errors"], indent=2, ensure_ascii=False)}

The validation result above is produced by the real execution environment.

Every error message is factual.

If the validation says a parameter is unsupported,
remove or replace that parameter.

If the current file contains a line that caused the validation error,
you MUST delete or replace that line.

Never keep unsupported parameters.

If validation says

Unsupported parameters for module:
timeout

the output MUST NOT contain

timeout:

# REQUIRED FIXES

{error_summary}

===== REAL VALIDATION LOG =====

{validation_log}

The validation result above is produced by the real execution environment.

Every error message is factual.

If the validation says a parameter is unsupported,
remove or replace that parameter.

Never output code that still contains the same validation error.

# stdout

{context_data.get("stdout","")}

# stderr

{context_data.get("stderr","")}

- Use ONLY modules available in the validation environment.
- Use fully qualified collection names (FQCN).
- Do NOT invent module names.
- Preserve all previous fixes.
- Modify only the lines related to the validation error.

Target file:
{path}

Fix ONLY this file.
You MUST preserve every previous fix unless the validation log explicitly says that fix is wrong.
Do NOT revert previously corrected lines.
Modify only the lines directly related to the reported validation errors.
Use the validation stdout/stderr as the highest priority source of truth.
Return ONLY file content.
Do NOT return JSON.
Do NOT regenerate other files.
Do NOT explain your changes.
Do NOT use Markdown.

The validation log above is the only source of truth.
Fix every error reported there.
Do not guess.
Do not repeat the same validation error.
Return ONLY the corrected file.
Before returning,
verify that every validation error has disappeared.

If any reported invalid parameter still exists,
your answer is incorrect.

Do not return it.
    
Current file

{current_file}

# Architecture

{architecture}

# System Rules

{rules}

# Output Format

{format_rules}

Priority 1
Validation Log

Priority 2
Current File

Priority 3
Architecture

Priority 4
Output Rules

================================================
FINAL INSTRUCTIONS (HIGHEST PRIORITY)

The validation log is the single source of truth.

If the validation reports:

Unsupported parameters:
timeout

then the returned file MUST NOT contain:

timeout:

Do not keep unsupported parameters under any circumstance.

Return ONLY the corrected file.
"""

    print("Calling Ollama...")

    try:

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role":"system",
                    "content": Path(
                        "prompts/php_engineer.txt"
                    ).read_text(
                        encoding="utf-8"
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0
        )

        print("Ollama returned.")

    except Exception as e:

        print("OLLAMA ERROR")
        print(e)
        raise

    content = response.choices[0].message.content
    print("=== REGENERATE END ===")

    if content is None:
        raise RuntimeError("Empty response from model")

    print("===== REGENERATED FILE =====")
    print(content)
    print("============================")

    return strip_markdown_fence(content).strip()

# =========================================================
# YAML Repair
# =========================================================

def repair_yaml_text(
    text: str
) -> str:

    import re

    # -------------------------------------------------
    # normalize jinja spacing
    # -------------------------------------------------

    text = re.sub(
        r"\{\{\s*([^\}]+)\s*\}\}",
        r"{{ \1 }}",
        text
    )

    # -------------------------------------------------
    # key merge repair
    # db: x    next:
    # -------------------------------------------------

    text = re.sub(
        r"([^\n])(\s+[A-Za-z_][A-Za-z0-9_]*:)",
        r"\1\n\2",
        text
    )

    # -------------------------------------------------
    # task merge repair
    # - name: xxx      module:
    # -------------------------------------------------

    text = re.sub(
        r"(- name:[^\n]+)\s+([a-zA-Z0-9_.]+:)",
        r"\1\n  \2",
        text
    )

    # -------------------------------------------------
    # owner/group collapse repair
    # owner: xgroup:
    # -------------------------------------------------

    text = re.sub(
        r"([^\n])(group:)",
        r"\1\n\2",
        text
    )

    # -------------------------------------------------
    # malformed jinja recovery
    # "{{ app_dir }}/x
    # -------------------------------------------------

    text = re.sub(
        r'"{{\s*([^}]+)\s*}}([^"\n]*)',
        r'"{{ \1 }}\2"',
        text
    )

    return text

def strip_markdown_fence(
    text: str
) -> str:

    text = text.strip()

    text = re.sub(
        r"^```[a-zA-Z]*\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return text.strip()


# =========================================================
# ENV
# =========================================================

load_dotenv()


# =========================================================
# OpenAI Client
# =========================================================

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=900
)


# =========================================================
# Load Context
# =========================================================

print("\n===== LOAD CONTEXT =====")

architecture = Path(
    "context/architecture.md"
).read_text(encoding="utf-8")

rules = Path(
    "context/system_rules.md"
).read_text(encoding="utf-8")

format_rules = Path(
    "context/output_format.md"
).read_text(encoding="utf-8")

review_rules = Path(
    "context/reviewer_rules.md"
).read_text(encoding="utf-8")

reviewer_prompt = Path(
    "prompts/reviewer.txt"
).read_text(encoding="utf-8")

task = Path(
    "context/task.md"
).read_text(encoding="utf-8")


print("Context loaded")

# =========================================================
# Schema
# =========================================================

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string"
        },
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    },
                    "content": {
                        "type": "string"
                    }
                },
                "required": [
                    "path",
                    "content"
                ],
                "additionalProperties": False
            }
        },
        "commands": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": [
        "summary",
        "files",
        "commands",
        "risks"
    ],
    "additionalProperties": False
}


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {
            "type": "boolean"
        },
        "summary": {
            "type": "string"
        },
        "risks": {
            "type": "array",
            "items": {
                "anyOf": [
                    {
                        "type": "string"
                    },
                    {
                        "type": "object",
                        "properties": {
                            "severity": {
                                "type": "string"
                            },
                            "description": {
                                "type": "string"
                            },
                            "location": {
                                "type": "string"
                            },
                            "fix": {
                                "type": "string"
                            }
                        }
                    }
                ]
            }
        }
    },
    "required": [
        "approved",
        "summary",
        "risks"
    ],
    "additionalProperties": False
}


# =========================================================
# Prompt
# =========================================================

print("\n===== GENERATE PROMPT =====")


prompt = f"""
# Architecture

{architecture}

# Rules

{rules}

# Output Format

{format_rules}

# Task

{task}

"""

print(f"Prompt length = {len(prompt):,} chars")

# =========================================================
# Generate
# =========================================================

system_prompt = Path(
    "prompts/architect.txt"
).read_text(
    encoding="utf-8"
)

print("\n===== GENERATE START =====")
start = time.time()

print("Calling Ollama...")

try:

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0,
        max_tokens=8192
    #    stop=[
    #       "\n```"
    #    ]
    )
    print("Ollama returned")

except Exception as e:
    print("Ollama call failed")
    raise RuntimeError(
        f"Failed to call Ollama: {e}"
    )

elapsed = time.time() - start
print(f"Generate finished ({elapsed:.1f}s)")

choice = response.choices[0]

print(choice)

raw_output = (
    choice.message.content
    or getattr(choice.message, "reasoning_content", None)
)

print("finish_reason =", response.choices[0].finish_reason)
print(response.choices[0])
print("content =", repr(raw_output))

if not raw_output:

    if choice.finish_reason == "length":
        raise RuntimeError(
            "Generation reached max_tokens before producing output. "
            "Increase max_tokens or disable thinking mode."
        )

    raise RuntimeError(
        "Model returned empty response."
    )


json_text = extract_json(raw_output)

json_text = sanitize_json_string(
    json_text
)

data = safe_json_loads(json_text)

required_defaults = {
    "commands": [],
    "risks": [],
    "files": [],
    "summary": ""
}

for key, default in required_defaults.items():
    data.setdefault(key, default)

try:
    validate(
        instance=data,
        schema=OUTPUT_SCHEMA
    )

except ValidationError as e:

    print("\nSchema validation failed")
    print(e)

    regeneration_context = {
        "source": "schema",
        "errors": [str(e)]
    }

    target_file = "all"

    regenerated = regenerate_file_with_context(
        target_file,
        architecture,
        regeneration_context
    )

    data = safe_json_loads(regenerated)

    validate(
        instance=data,
        schema=OUTPUT_SCHEMA
    )

if not isinstance(data, dict):
    raise RuntimeError(
        "Generated result must be object"
    )


# =========================================================
# Review Loop
# =========================================================

retry_count = 0

while True:
    print("\n===== REVIEW =====")
    print(f"Attempt {retry_count+1}")

    review_request = f"""
Generated JSON:

{json.dumps(data, ensure_ascii=False)}

Review it.
Return JSON only.
"""

    print(
        f"\n=== REVIEW ATTEMPT {retry_count + 1} ==="
    )

    print("Review request...")
    start = time.time()

    review_response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": reviewer_prompt
            },
            {
                "role": "user",
                "content": review_request
            }
        ],
        temperature=0.0
    )

    print(
        f"Review finished "
        f"({time.time()-start:.1f}s)"
    )

    response.choices[0].message.content

    review_raw =  (
        review_response
        .choices[0]
        .message
        .content
    )

    print("\n=== REVIEW RAW ===")
    print(review_raw)

    review_json = extract_json(
        review_raw
    )

    review_json = sanitize_json_string(
        review_json
    )

    review_data = safe_json_loads(
        review_json
    )

    try:
        validate(
            instance=review_data,
            schema=REVIEW_SCHEMA
        )

    except ValidationError as e:
        raise RuntimeError(
            f"Review schema invalid:\n{e}"
        )

    risks = review_data.get(
        "risks",
        []
    )

    blocking = []

    for r in risks:

        if not isinstance(r, dict):
            blocking.append({
                "severity": "WARNING",
                "description": r
            })

            continue

        severity = r.get("severity")

        if severity in BLOCKING_SEVERITIES:
            blocking.append(r)

    if not blocking:

        print(
            "\nReview passed"
        )

        break

    # approved=true なら通す
    if review_data.get("approved", True):

        print(
            "\nReview approved with warnings"
        )

        break

    retry_count += 1

    if retry_count >= MAX_RETRY:

        print(
            "\nMax retry reached"
        )

        print(
            "Continue pipeline with warnings"
        )

        break

    print(
        "\nBlocking risks found"
    )

    fix_prompt = f"""
Fix this JSON.

Current JSON:

{json.dumps(data, ensure_ascii=False)}

Errors:

{json.dumps(blocking, ensure_ascii=False)}

Return JSON only.
"""

    retry_temp = max(
        0.05,
        0.3 - (retry_count * 0.1)
    )

    fix_response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": Path(
                    "prompts/fixer.txt"
                ).read_text(
                    encoding="utf-8"
                )
            },
            {
                "role": "user",
                "content": fix_prompt
            }
        ],
        temperature=retry_temp
    )

    fix_raw =  (
        fix_response
        .choices[0]
        .message
        .content
    )

    print("\n=== FIX RAW ===")
    print(fix_raw)

    fixed_json = extract_json(
        fix_raw
    )

    fixed_json = sanitize_json_string(
        fixed_json
    )

    data = safe_json_loads(
        fixed_json
    )

    try:
        validate(
            instance=data,
            schema=OUTPUT_SCHEMA
        )

    except ValidationError as e:
        raise RuntimeError(
            f"Fixed JSON schema invalid:\n{e}"
        )

    required_paths = {
        "ansible/playbook.yml",
        "ansible/inventory.ini",
        "src/index.php"
    }

    generated_paths = {
        f["path"]
        for f in data["files"]
    }

    missing = required_paths - generated_paths

    if missing:
        print(f"Missing files: {missing}")

        for path in missing:

            content = regenerate_file(path)

            data["files"].append({
                "path": path,
                "content": content
            })

# =========================================================
# Save Logs
# =========================================================

timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

log_text(
    Path(
        f"logs/ai_run_{timestamp}.txt"
    ),
    raw_output or ""
)

log_text(
    Path(
        f"generated/runtime/output_{timestamp}.json"
    ),
    json.dumps(
        data,
        indent=2,
        ensure_ascii=False
    )
)

log_text(
    Path(
        f"generated/runtime/review_{timestamp}.json"
    ),
    json.dumps(
        review_data,
        indent=2,
        ensure_ascii=False
    )
)

print("\nSaved logs")

def regenerate_file_only(path: str) -> str:

    prompt = f"""
path:
{path}

重要:
- ファイル本文のみ
- markdown禁止
- explanation禁止
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0
    )

    content = response.choices[0].message.content

    if content is None:
        raise RuntimeError("Empty response from model")

    return strip_markdown_fence(content).strip()


# =========================================================
# Validation Helpers
# =========================================================

import base64

from difflib import (
    get_close_matches
)

KNOWN_YAML_KEYS = {

    "pod_name",
    "mysql_container_name",
    "web_container_name",
    "mysql_root_password",
    "mysql_image",
    "web_image",
    "html_dir",
    "web_port",
    "mysql_db"

}

KNOWN_PATHS = [
    "/home/vboxuser/containers/html",
    "/home/vboxuser/containers/html/index.php",
    "/home/vboxuser/containers/mysql"
]

BASE64_RE = re.compile(
    r"^[A-Za-z0-9+/=\r\n]+$"
)

def validate_base64(data: str) -> bool:

    if not data:
        return False

    data = data.strip()

    if not BASE64_RE.match(data):
        return False

    try:

        base64.b64decode(
            data,
            validate=True
        )

        return True

    except Exception:

        return False

def semantic_yaml_check(obj):

    problems = []

    def walk(x):

        if isinstance(x, dict):

            for k, v in x.items():

                matches = get_close_matches(
                    k,
                    KNOWN_YAML_KEYS,
                    n=1,
                    cutoff=0.80
                )

                if (
                    matches
                    and k != matches[0]
                ):

                    problems.append(
                        f"Possible typo: "
                        f"{k} -> {matches[0]}"
                    )

                walk(v)

        elif isinstance(x, list):

            for i in x:

                walk(i)

    walk(obj)

    return problems

def run_validation():

    validation_errors = []

    import yaml

    try:

        if not playbook_file.exists():

            validation_errors.append({
                "type": "missing_playbook",
                "file": str(playbook_file)
            })

        else:

            parsed = yaml.safe_load(
                playbook_file.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(parsed, list):
                validation_errors.append({
                    "type": "invalid_playbook",
                    "file": str(playbook_file),
                    "stderr": "Playbook must be a YAML list."
                })

    except Exception as e:

        validation_errors.append({
            "type": "yaml_parse",
            "file": str(playbook_file),
            "stderr": str(e)
        })

    validation_errors.extend(
        validate_cross_file_consistency()
    )

    if inventory_file.exists() and playbook_file.exists():

        remote_cmd = (
            f"cd {REMOTE_PROJECT_ROOT} && "
            "ansible-playbook "
            "-i ansible/inventory.ini "
            "ansible/playbook.yml "
            "--check"
        )

        code, stdout, stderr = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            remote_cmd
        )

        if code != 0:

            validation_errors.append({
                "type": "ansible_syntax",
                "file": str(playbook_file),
                "stdout": stdout,
                "stderr": stderr
            })

    print("RETURN ERROR COUNT =", len(validation_errors))

    return validation_errors, stdout, stderr

def validate_known_paths(text):

    problems = []

    path_pattern = r"/home/[^\s\"']+"

    paths = re.findall(
        path_pattern,
        text
    )

    for p in paths:

        match = get_close_matches(
            p,
            KNOWN_PATHS,
            n=1,
            cutoff=0.85
        )

        if match and p != match[0]:

            problems.append(
                f"Possible path typo: "
                f"{p} -> {match[0]}"
            )

    return problems

def validate_cross_file_consistency():

    errors = []

    if (
        not playbook_file.exists()
        or
        not php_file.exists()
    ):
        return errors

    playbook_text = playbook_file.read_text(
        encoding="utf-8"
    )

    php_text = php_file.read_text(
        encoding="utf-8"
    )

    mysql_db = re.search(
        r"MYSQL_DATABASE=(\w+)",
        playbook_text
    )

    php_db = re.search(
        r'\$db\s*=\s*"([^"]+)"',
        php_text
    )

    if (
        mysql_db
        and
        php_db
        and
        mysql_db.group(1)
        !=
        php_db.group(1)
    ):

        errors.append({
            "type": "cross_file",
            "playbook_db":
                mysql_db.group(1),
            "php_db":
                php_db.group(1)
        })

    return errors


def run_remote_deploy():

    print()

    print("===== DEPLOY =====")

    remote_cmd = (

        f"cd {REMOTE_PROJECT_ROOT} && "

        "ansible-playbook "

        "-i ansible/inventory.ini "

        "ansible/playbook.yml"

    )

    code, stdout, stderr = run_remote_command(
        ANSIBLE_CONTROL_NODE,
        remote_cmd
    )

    stdout = stdout or ""
    stderr = stderr or ""

    print(stdout)

    if stderr:
        print(stderr)

    print("Return code =", code)

    return {
        "success": code == 0,
        "stdout": stdout,
        "stderr": stderr
    }



# =========================================================
# Generate Files
# =========================================================

validation_errors = []

import shutil

if SAFE_ROOT.exists():

    shutil.rmtree(SAFE_ROOT)

SAFE_ROOT.mkdir(
    parents=True,
    exist_ok=True
)

print(f"SAFE_ROOT = {SAFE_ROOT}")


for file in data.get("files", []):

    try:

        import yaml

        relative_path = file.get("path")

        print(
            f"\n===== FILE ===== "
            f"{relative_path}"
        )

        if relative_path:
            relative_path = relative_path.strip()

        content = file.get(
            "content"
        )

        if not relative_path:

            print("Skip invalid path")
            continue

        if not content:
            print(
                f"Skip empty content: {relative_path}"
            )
            continue

        # # =================================================
        # # Base64 validation
        # # =================================================

        # if not validate_base64(decode_b64):
        #     print(
        #         f"Invalid base64 detected: {relative_path}"
        #     )

        #     raise ValueError(
        #         f"Broken base64: {relative_path}"
        #     )

        # # =================================================
        # # Base64 decode
        # # =================================================

        # try:

        #     content = content

        # except Exception:

        #     print(
        #         f"\n=== BROKEN BASE64 DETECTED ===\n"
        #         f"{relative_path}"
        #     )

        #     file_regen_prompt = f"""
        # 以下ファイルを再生成してください。

        # path:
        # {relative_path}

        # 重要:
        # - content本体を生成
        # - base64ではなく生テキスト生成
        # - markdown禁止
        # - explanation禁止

        # 返却はファイル内容のみ
        # """


        #     content = regenerate_file_with_context(
        #         relative_path,
        #         architecture,
        #         review_data
        #     )

        #     print(
        #         "\n=== BASE64 AUTO FIXED ==="
        #     )

            

        # # UTF-8 normalize
        # content = content.encode(
        #     "utf-8",
        #     errors="ignore"
        # ).decode(
        #     "utf-8",
        #     errors="ignore"
        # )

        # # remove dangerous control chars only
        # content = "".join(
        #     c for c in content
        #     if (
        #         c == "\n"
        #         or c == "\r"
        #         or c == "\t"
        #         or ord(c) >= 32
        #     )
        # )

        # # tab -> spaces
        # content = content.replace(
        #     "\t",
        #     "    "
        # )

        # # normalize newline
        # content = content.replace(
        #     "\r\n",
        #     "\n"
        # )

        # content = content.replace(
        #     "\r",
        #     "\n"
        # )

        # =================================================
        # YAML targeted repair
        # =================================================

        if relative_path.endswith(
            (".yml", ".yaml")
        ):

            print("===== BEFORE REPAIR =====")
            print(content)

            # content = repair_yaml_text(
            #     content
            # )

            print("===== AFTER REPAIR =====")
            print(content)

        if not content.strip():

            raise ValueError(
                f"Empty content file: {relative_path}"
            )

        if relative_path not in ALLOWED_PATHS:

            raise ValueError(
                f"Forbidden path: {relative_path}"
            )

        # =================================================
        # YAML validation before save
        # =================================================

        if relative_path.endswith(
            (".yml", ".yaml")
        ):

            try:

                parsed_yaml = yaml.safe_load(
                    content
                )

            except yaml.YAMLError:

                try:

                    content = repair_yaml_text(
                        content
                    )

                    parsed_yaml = yaml.safe_load(
                        content
                    )

                    print(
                        "\n=== YAML REPAIRED LOCALLY ==="
                    )

                except yaml.YAMLError as e:

                    print(
                        "\n=== INVALID YAML BEFORE SAVE ==="
                    )

                    print(content)

                    yaml_fix_prompt = f"""
Fix this YAML.

Return YAML only.

{content}

Error:
{e}
"""

                    import time

                    fix_yaml_response = None

                    for attempt in range(3):
                        try:
                            fix_yaml_response = (
                                client.chat.completions.create(
                                    model=MODEL_NAME,
                                    messages=[
                                        {
                                            "role":"system",
                                            "content": Path(
                                                "prompts/fixer.txt"
                                            ).read_text(
                                                encoding="utf-8"
                                            )
                                        },
                                        {
                                            "role":"user",
                                            "content":yaml_fix_prompt
                                        }
                                    ],
                                    temperature=0.0
                                )
                            )
                        
                        except Exception as e:
                            
                            if "503" in str(e):
                                print(
                                    f"[WARN] Gemini 503 retry={attempt+1}/3"
                                )
                                time.sleep(10)
                                continue

                            raise

                    if fix_yaml_response is None:
                        raise RuntimeError(
                            "Gemini fix_yaml failed after 3 retries"
                        )


                    content = (
                        fix_yaml_response
                        .choices[0]
                        .message
                        .content
                    )

                    content = strip_markdown_fence(content)

                    # markdown除去
                    content = re.sub(
                        r"^```yaml\s*",
                        "",
                        content,
                        flags=re.MULTILINE
                    )

                    content = re.sub(
                        r"^```\s*",
                        "",
                        content,
                        flags=re.MULTILINE
                    )

                    content = re.sub(
                        r"\s*```$",
                        "",
                        content
                    )

                    print(
                        "\n=== YAML AUTO FIXED ==="
                    )

                    print(content)

                    parsed_yaml = yaml.safe_load(
                        content
                    )



                    # =============================================
                    # Semantic YAML validation
                    # =============================================

                    semantic_problems = (
                        semantic_yaml_check(
                            parsed_yaml
                        )
                    )

                    if semantic_problems:

                        print(
                            "\n=== SEMANTIC WARNINGS ==="
                        )

                        for p in semantic_problems:

                            print(p)

        if relative_path.endswith(
            (".yml", ".yaml")
        ):

            path_problems = validate_known_paths(
                content
            )

            for p in path_problems:

                validation_errors.append({
                    "type": "path_typo",
                    "detail": p
                })

        print(f"Decoded size : {len(content)}")
        print(content[:300])

        safe_write_file(
            SAFE_ROOT,
            relative_path,
            content
        )

    except Exception as e:

        print(
            f"Failed writing {relative_path}"
        )

        print(e)

        validation_errors.append({
            "type": "yaml_autofix_failed",
            "file": str(
                SAFE_ROOT / relative_path
            ),
            "stderr": str(e)
        })

        continue

# =========================================================
# Common Paths
# =========================================================

inventory_file = (
    SAFE_ROOT / "ansible/inventory.ini"
)

playbook_file = (
    SAFE_ROOT / "ansible/playbook.yml"
)

php_file = (
    SAFE_ROOT / "src/index.php"
)

# =========================================================
# Validation
# =========================================================

print("\n=== VALIDATION ===")

playbook_path = (
    SAFE_ROOT /
    "ansible" /
    "playbook.yml"
)

# # ---------------------------------------------------------
# # PHP Lint
# # ---------------------------------------------------------

# php_file = (
#     SAFE_ROOT / "html/index.php"
# )

# if php_file.exists():

#     print("\nRunning PHP lint...")

#     code, stdout, stderr = run_command(
#         [
#             "php",
#             "-l",
#             str(php_file)
#         ]
#     )

#     print(stdout)
#     print(stderr)

#     if code != 0:

#         validation_errors.append({
#             "type": "php_lint",
#             "file": str(php_file),
#             "stderr": stderr
#         })

# # ---------------------------------------------------------
# # Ansible Syntax Check
# # ---------------------------------------------------------

# inventory_file = (
#     SAFE_ROOT / "ansible/inventory.ini"
# )

# playbook_file = (
#     SAFE_ROOT / "ansible/playbook.yml"
# )

# if (
#     inventory_file.exists()
#     and playbook_file.exists()
# ):

#     print("\nRunning ansible syntax check...")

#     code, stdout, stderr = run_command(
#         [
#             "ansible-playbook",
#             "-i",
#             str(inventory_file),
#             str(playbook_file),
#             "--syntax-check"
#         ]
#     )

#     print(stdout)
#     print(stderr)

#     if code != 0:

#         validation_errors.append({
#             "type": "ansible_syntax",
#             "file": str(playbook_file),
#             "stderr": stderr
#         })

# ---------------------------------------------------------
# YAML Parse Check
# ---------------------------------------------------------

try:

    import yaml

    if not playbook_file.exists():

        validation_errors.append({
            "type": "missing_playbook",
            "file": str(playbook_file)
        })

    else:

        print("\n=== PLAYBOOK CONTENT ===")
        print(
            playbook_file.read_text(
                encoding="utf-8"
            )
        )

        playbook_text = playbook_file.read_text(
            encoding="utf-8"
        )

        print(repr(playbook_text))

        yaml.safe_load(
            playbook_file.read_text(
                encoding="utf-8"
            )
        )

        print("YAML parse ok")

    if not inventory_file.exists():

        validation_errors.append({
            "type": "missing_inventory",
            "file": str(inventory_file)
        })

    else:

        inventory_text = inventory_file.read_text(
            encoding="utf-8"
        )

        if "asbsvr" not in inventory_text \
        or "rockey8" not in inventory_text:

            validation_errors.append({
                "type": "invalid_inventory",
                "file": str(inventory_file),
                "stderr": "Inventory format is invalid."
            })

    if not playbook_file.exists():

        validation_errors.append({
            "type": "missing_playbook",
            "file": str(playbook_file)
        })

    if not php_file.exists():

        validation_errors.append({
            "type": "missing_php",
            "file": str(php_file)
        })

except Exception as e:

    validation_errors.append({
        "type": "yaml_parse",
        "file": str(playbook_file),
        "stderr": str(e)
    })

# ---------------------------------------------------------
# Upload generated files
# ---------------------------------------------------------

print("Remote validation...")

run_command([
    "scp",
    "-r",
    str(SAFE_ROOT),
    f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated"
])


# # ---------------------------------------------------------

# # Remote Ansible Syntax Check

# # ---------------------------------------------------------

# if (
#     inventory_file.exists()
#     and playbook_file.exists()
# ):

#     base_cmd = (
#         "which ansible-playbook && "
#         "ansible-playbook --version && "
#         "ansible-galaxy collection list && "
#         f"cd {REMOTE_PROJECT_ROOT} && "
#     )

#     print("\nRunning remote ansible syntax check...")

#     syntax_cmd = (
#         base_cmd
#         + "ansible-playbook "
#         "-i ansible/inventory.ini "
#         "ansible/playbook.yml "
#         "--syntax-check"
#     )

#     code, stdout, stderr = run_remote_command(
#         ANSIBLE_CONTROL_NODE,
#         syntax_cmd
#     )

#     if code != 0:

#         validation_errors.append({
#             "type": "ansible_check",
#             "file": str(playbook_file),
#             "stdout": stdout,
#             "stderr": stderr
#         })

#     print("\nRunning remote ansible check mode...")

#     check_cmd = (
#         base_cmd
#         + "ansible-playbook "
#         "-i ansible/inventory.ini "
#         "ansible/playbook.yml "
#         "--check"
#     )

#     code, stdout, stderr = run_remote_command(
#         ANSIBLE_CONTROL_NODE,
#         check_cmd
#     )

#     stdout = stdout or ""
#     stderr = stderr or ""

#     print(stdout if stdout else "")
#     print(stderr if stderr else "")
    
#     print("RETURN CODE =", code)

#     if code != 0:

#         ssh_errors = [
#             "Connection timed out",
#             "Could not resolve hostname",
#             "Connection refused",
#             "No route to host",
#             "Permission denied",
#             "password:"
#         ]

#         if stderr and any(
#             x in stderr
#             for x in ssh_errors
#         ):

#             print(
#                 "\nSSH connection unavailable"
#             )

#             print(
#                 "Skip remote validation"
#             )

#         else:
#             validation_errors.append({
#                 "type": "ansible_syntax",
#                 "file": str(playbook_file),
#                 "stdout": stdout,
#                 "stderr": stderr
#             })

#         print("ERROR COUNT =", len(validation_errors))

#     else:

#         check_cmd = (
#             f"cd {REMOTE_PROJECT_ROOT} && "
#             "ansible-playbook "
#             "-i ansible/inventory.ini "
#             "ansible/playbook.yml "
#             "--check"
#         )

#         code, stdout, stderr = run_remote_command(
#             ANSIBLE_CONTROL_NODE,
#             check_cmd
#         )

#         print("RETURN CODE =", code)

#         if code != 0:

#             validation_errors.append({
#                 "type": "ansible_check",
#                 "file": str(playbook_file),
#                 "stdout": stdout,
#                 "stderr": stderr
#             })

#         print("ERROR COUNT =", len(validation_errors))

# print("Remote validation finished")


# # ---------------------------------------------------------

# # Remote PHP Lint

# # ---------------------------------------------------------

# if php_file.exists():

#     print("\nRunning remote PHP lint...")

#     remote_cmd = (
#         "php -l "
#         "/home/vboxuser/containers/html/index.php"
#     )

#     code, stdout, stderr = run_remote_command(
#         EXECUTION_NODE,
#         remote_cmd
#     )

#     print(stdout)
#     print(stderr)

#     if code != 0:

#         validation_errors.append({
#             "type": "php_lint",
#             "stderr": stderr
#         })


# ---------------------------------------------------------
# Validation Result
# ---------------------------------------------------------

validation_errors, stdout, stderr = run_validation()

if validation_errors:

    print("\n=== VALIDATION FAILED ===")

    for err in validation_errors:

        print(json.dumps(
            err,
            indent=2,
            ensure_ascii=False
        ))

MAX_VALIDATION_RETRY = 3

validation_success = False

for attempt in range(MAX_VALIDATION_RETRY):

    print(
        f"\n===== VALIDATION ATTEMPT {attempt + 1} ====="
    )

    validation_errors, stdout, stderr = run_validation()

    print("ERROR COUNT =", len(validation_errors))

    for e in validation_errors:
        print(e["type"])

    if not validation_errors:

        print(
            f"Validation success "
            f"attempt={attempt+1}"
        )
        validation_success = True
        break

    regeneration_context = {
        "source": "validation",
        "errors": validation_errors,
        "stdout": stdout,
        "stderr": stderr
    }

    for err in validation_errors:

        file_value = err.get("file")

        if file_value:
            try:
                target_file = str(
                    Path(file_value).resolve().relative_to(
                        SAFE_ROOT.resolve()
                    )
                )
            except ValueError:
                target_file = "ansible/playbook.yml"
        else:
            target_file = "ansible/playbook.yml"

        print(f"[ERROR] {target_file}")

        print("BEFORE REGENERATE")

        regenerated = regenerate_file_with_context(
            target_file,
            architecture,
            regeneration_context
        )
        print("AFTER REGENERATE")
        print("===== REGENERATED HEAD =====")
        print(regenerated)

        safe_write_file(
            SAFE_ROOT,
            target_file,
            regenerated
        )

        print("AFTER WRITE")
        print("===== FILE AFTER WRITE =====")
        print(
            (SAFE_ROOT / target_file)
            .read_text(encoding="utf-8")[:600]
        )

        code, stdout, stderr = run_command([
            "scp",
            "-r",
            str(SAFE_ROOT),
            f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated"
        ])

        print("AFTER SCP")

        print("SCP RETURN =", code)

        target_file = target_file.replace("\\", "/")
        
        code2, stdout2, stderr2 = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            f"sed -n '1,30p' {REMOTE_PROJECT_ROOT}/{target_file}"
        )

        print("===== REMOTE FILE =====")
        print(stdout2)

        if stdout:
            print(stdout)

        if stderr:
            print(stderr)

# =========================================================
# Deploy
# =========================================================

deploy_success = False

if validation_success:

    print("\nValidation passed")
    print(playbook_file.read_text())

    deploy_result = run_remote_deploy()

    deploy_success = deploy_result["success"]


# =========================================================
# Final
# =========================================================

if validation_success and deploy_success:

    print("\nPipeline completed successfully")

elif not validation_success:

    raise RuntimeError(
        "Validation retry exhausted"
    )

else:

    raise RuntimeError(
        "Deploy failed"
    )
