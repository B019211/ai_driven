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

        return json.loads(repaired)


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
        max_tokens=1200
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

    prompt = f"""
Errors:

{json.dumps(context_data["errors"], ensure_ascii=False)}

Target:

{path}

Return file content only.

Target file:
{path}

このファイルのみ再生成してください。

重要:
- ファイル本文のみ返却
"""

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

    content = response.choices[0].message.content

    if content is None:
        raise RuntimeError("Empty response from model")

    return strip_markdown_fence(content).strip()

    if not response.choices[0].message.content:
        raise RuntimeError(
            f"Gemini returned empty response for {path}"
        )

    return strip_markdown_fence(
        response.choices[0].message.content
    ).strip()

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
    timeout=1800
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

現在は learning phase です。

目的:
- CI/CDパイプライン完走
- JSON安定生成
- review loop安定化
- file生成成功

本番品質より、
最後まで通ることを優先してください。

現在の構成を改善してください。

以下をJSONで返してください:

- summary
- files
- commands
- risks

filesには生成すべきファイルを含めてください。

生成可能なpathは以下のみ:

* ansible/playbook.yml
* ansible/inventory.ini
* src/index.php

それ以外のpathは禁止。

特に:

* deploy.yml
* html/index.php
* 任意path
  は禁止。

inventory.ini の hostname は:

* asbsvr
* rockey8
  のみ使用可能。

重要:
- filesの各要素は "path" と "content" のみ含めること
- contentにはUTF-8テキストをそのまま格納すること
- Base64は禁止
- UTF-8 printable text only
- 制御文字禁止
- binary禁止
- markdown禁止
- JSON only
- YAMLは厳密構文
- YAML literal only
- YAML indentation must use 2 spaces only

- Every YAML key must start at line head



- Generate strictly valid YAML


- ansible module行の改行省略禁止
- "{{ variable }}" は必ずダブルクォートで囲む
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
    temperature=0.1,
    max_tokens=1200,
    stop=[
       "\n```"
    ]
)

elapsed = time.time() - start
print(f"Generate finished ({elapsed:.1f}s)")

raw_output = response.choices[0].message.content

print("\n=== RAW OUTPUT ===")
print(raw_output[:3000])

if len(raw_output) > 3000:
    print("\n...(truncated)...")

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
    raise RuntimeError(
        f"Output schema validation failed:\n{e}"
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
            "--syntax-check"
        )

        code, stdout, stderr = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            remote_cmd
        )

        if code != 0:

            validation_errors.append({
                "type": "ansible_syntax",
                "file": str(playbook_file),
                "stderr": stderr
            })

    return validation_errors

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

        # if not validate_base64(content_b64):

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

        #     decoded = content

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


        #     decoded = regenerate_file_with_context(
        #         relative_path,
        #         architecture,
        #         review_data
        #     )

        #     print(
        #         "\n=== BASE64 AUTO FIXED ==="
        #     )

            

        # # UTF-8 normalize
        # decoded = decoded.encode(
        #     "utf-8",
        #     errors="ignore"
        # ).decode(
        #     "utf-8",
        #     errors="ignore"
        # )

        # # remove dangerous control chars only
        # decoded = "".join(
        #     c for c in decoded
        #     if (
        #         c == "\n"
        #         or c == "\r"
        #         or c == "\t"
        #         or ord(c) >= 32
        #     )
        # )

        # # tab -> spaces
        # decoded = decoded.replace(
        #     "\t",
        #     "    "
        # )

        # # normalize newline
        # decoded = decoded.replace(
        #     "\r\n",
        #     "\n"
        # )

        # decoded = decoded.replace(
        #     "\r",
        #     "\n"
        # )

        # =================================================
        # YAML targeted repair
        # =================================================

        if relative_path.endswith(
            (".yml", ".yaml")
        ):

            decoded = repair_yaml_text(
                decoded
            )

        if not decoded.strip():

            raise ValueError(
                f"Empty decoded file: {relative_path}"
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
                    decoded
                )

            except yaml.YAMLError:

                try:

                    decoded = repair_yaml_text(
                        decoded
                    )

                    parsed_yaml = yaml.safe_load(
                        decoded
                    )

                    print(
                        "\n=== YAML REPAIRED LOCALLY ==="
                    )

                except yaml.YAMLError as e:

                    print(
                        "\n=== INVALID YAML BEFORE SAVE ==="
                    )

                    print(decoded)

                    yaml_fix_prompt = f"""
Fix this YAML.

Return YAML only.

{decoded}

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


                    decoded = (
                        fix_yaml_response
                        .choices[0]
                        .message
                        .content
                    )

                    decoded = strip_markdown_fence(decoded)

                    # markdown除去
                    decoded = re.sub(
                        r"^```yaml\s*",
                        "",
                        decoded,
                        flags=re.MULTILINE
                    )

                    decoded = re.sub(
                        r"^```\s*",
                        "",
                        decoded,
                        flags=re.MULTILINE
                    )

                    decoded = re.sub(
                        r"\s*```$",
                        "",
                        decoded
                    )

                    print(
                        "\n=== YAML AUTO FIXED ==="
                    )

                    print(decoded)

                    parsed_yaml = yaml.safe_load(
                        decoded
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
                decoded
            )

            for p in path_problems:

                validation_errors.append({
                    "type": "path_typo",
                    "detail": p
                })

        print(f"Decoded size : {len(decoded)}")
        print(decoded[:300])

        safe_write_file(
            SAFE_ROOT,
            relative_path,
            decoded
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


# ---------------------------------------------------------

# Remote Ansible Syntax Check

# ---------------------------------------------------------

if (
    inventory_file.exists()
    and playbook_file.exists()
):

    print(
        "\nRunning remote ansible syntax check..."
    )

    remote_cmd = (
        "which ansible-playbook && "
        "ansible-playbook --version && "
        "ansible-galaxy collection list && "
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

    stdout = stdout or ""
    stderr = stderr or ""

    print(stdout if stdout else "")
    print(stderr if stderr else "")

    if code != 0:

        ssh_errors = [
            "Connection timed out",
            "Could not resolve hostname",
            "Connection refused",
            "No route to host",
            "Permission denied",
            "password:"
        ]

        if stderr and any(
            x in stderr
            for x in ssh_errors
        ):

            print(
                "\nSSH connection unavailable"
            )

            print(
                "Skip remote validation"
            )

        else:
            validation_errors.append({
                "type": "ansible_syntax",
                "file": str(playbook_file),
                "stderr": stderr
            })

print("Remote validation finished")

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

    validation_errors = run_validation()

    if not validation_errors:

        print(
            f"Validation success "
            f"attempt={attempt+1}"
        )
        validation_success = True
        break

    regeneration_context = {
        "source": "validation",
        "errors": validation_errors
    }

    target_file = "ansible/playbook.yml"

    for err in validation_errors:

        file_path = err.get("file")

        if file_path:
            try:
                rel = (
                    Path(SAFE_ROOT)
                    .joinpath(file_path)
                    .resolve()
                    .relative_to(
                        Path(SAFE_ROOT).resolve()
                    )
                )
            except Exception:
                rel = file_path

            print(f"[ERROR] {rel}")

        else:
            print(err)


        regenerated = regenerate_file_with_context(
            target_file,
            architecture,
            regeneration_context
        )

        print("\n=== REGENERATED FILE ===")
        print(regenerated)

        file_value = err.get("file")

        if file_value:

            err_path = Path(file_value)

            try:
                relative_target = str(
                    err_path.relative_to(SAFE_ROOT)
                )
            except ValueError:
                relative_target = target_file

        else:
            relative_target = target_file


        print(f"[ERROR] {relative_target}")

        safe_write_file(
            SAFE_ROOT,
            relative_target,
            regenerated
        )

        run_command([
            "scp",
            "-r",
            str(SAFE_ROOT),
            f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated"
        ])

        continue


# =========================================================
# Final
# =========================================================

if validation_success:

    print("\nValidation passed")
    print("\nPipeline completed successfully")

else:

    print("\nValidation failed")
    raise RuntimeError(
        "Validation retry exhausted"
    )
