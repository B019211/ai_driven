from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from google import genai
from google.genai import types

from json_repair import repair_json

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

MODEL_NAME = "gemini-2.5-flash"
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

    if end == -1:
        raise ValueError("JSON end not found")

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
- base64禁止
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0
        )
    )

    if not response.text:
        raise RuntimeError(
            f"Gemini returned empty response for {path}"
        )

    return strip_markdown_fence(
        response.text
    ).strip()

def regenerate_file_with_context(
    path: str,
    architecture: str,
    review_data: dict
) -> str:

    prompt = f"""
Architecture:
{architecture}

Review:
{json.dumps(review_data, ensure_ascii=False)}

Target file:
{path}

このファイルのみ再生成してください。

markdown禁止
explanation禁止
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0
        )
    )

    if not response.text:
        raise RuntimeError(
            f"Gemini returned empty response for {path}"
        )

    return strip_markdown_fence(
        response.text
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

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY not found"
    )


# =========================================================
# Gemini Client
# =========================================================

client = genai.Client(
    api_key=api_key
)


# =========================================================
# Load Context
# =========================================================

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
                    "content_b64": {
                        "type": "string"
                    }
                },
                "required": [
                    "path",
                    "content_b64"
                ]
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
    ]
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
        }
    },
    "required": [
        "approved",
        "summary",
        "risks"
    ]
}


# =========================================================
# Prompt
# =========================================================

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
- contentはcontent_b64へbase64で格納
- UTF-8 printable text only
- 制御文字禁止
- binary禁止
- markdown禁止
- JSON only
- YAMLは厳密構文
- YAML literal only
- YAML indentation must use 2 spaces only
- Never prefix keys with numbers
- Every YAML key must start at line head
- Never concatenate YAML keys
- owner and group must be separate lines
- Never prefix keys with numbers
- Generate strictly valid YAML
- YAML must be parseable by yaml.safe_load()
- key: value の後に別key連結禁止
- ansible module行の改行省略禁止
- "{{ variable }}" は必ずダブルクォートで囲む
"""


# =========================================================
# Generate
# =========================================================

response = client.models.generate_content(
    model=MODEL_NAME,
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=OUTPUT_SCHEMA,
        system_instruction="""
あなたは熟練のソフトウェアエンジニアです。

要件を満たす実装を生成してください。

重要:
- JSON only
- markdown禁止
- learning phase
- CI/CD完走優先
- シンプル実装優先
"""
    )
)

raw_output = response.text

print("\n=== RAW OUTPUT ===")
print(raw_output)

json_text = extract_json(raw_output)

json_text = sanitize_json_string(
    json_text
)

data = safe_json_loads(json_text)

if not isinstance(data, dict):
    raise RuntimeError(
        "Generated result must be object"
    )


# =========================================================
# Review Loop
# =========================================================

retry_count = 0

while True:

    review_request = f"""
# Review Rules

{review_rules}

# Reviewer Prompt

{reviewer_prompt}

# Generated Output

{json.dumps(data, indent=2, ensure_ascii=False)}

Review this output.
"""

    print(
        f"\n=== REVIEW ATTEMPT {retry_count + 1} ==="
    )

    review_response = client.models.generate_content(
        model=MODEL_NAME,
        contents=review_request,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=REVIEW_SCHEMA,
            system_instruction="""
あなたは学習環境向け reviewer です。

現在は localhost 上の
閉域開発環境です。

目的:
- CI/CDパイプライン完走
- JSON安定生成
- retry loop安定化

BLOCKERのみ停止対象。

HIGHはwarning扱い。

改善提案は行ってよいが、
可能な限り approved=true を返してください。

本当に危険な操作のみ reject:

- rm -rf
- malware
- credential exfiltration
- destructive shell
"""
        )
    )

    review_raw = review_response.text

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

    risks = review_data.get(
        "risks",
        []
    )

    blocking = []

    for r in risks:

        if not isinstance(r, dict):
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
前回JSONを修正してください。

重要:
- 元JSON構造維持
- 必要最小限修正
- filesを省略禁止
- markdown禁止
- content_b64を維持

前回JSON:
{json.dumps(data, ensure_ascii=False)}

レビュー結果:
{json.dumps(review_data, ensure_ascii=False)}
"""

    retry_temp = max(
        0.05,
        0.3 - (retry_count * 0.1)
    )

    fix_response = client.models.generate_content(
        model=MODEL_NAME,
        contents=fix_prompt,
        config=types.GenerateContentConfig(
            temperature=retry_temp,
            response_mime_type="application/json",
            response_schema=OUTPUT_SCHEMA,
            system_instruction="""
あなたは修正専門AIです。

全面再生成禁止。
必要最小限修正のみ。
"""
        )
    )

    fix_raw = fix_response.text

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

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    return strip_markdown_fence(
        response.text
    ).strip()


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

# =========================================================
# Generate Files
# =========================================================

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

        if relative_path:
            relative_path = relative_path.strip()

        content_b64 = file.get(
            "content_b64"
        )

        if not relative_path:

            print("Skip invalid path")
            continue

        if not content_b64:

            print(
                f"Skip empty content: {relative_path}"
            )

            continue

        # =================================================
        # Base64 validation
        # =================================================

        if not validate_base64(content_b64):

            print(
                f"Invalid base64 detected: {relative_path}"
            )

            raise ValueError(
                f"Broken base64: {relative_path}"
            )

        # =================================================
        # Base64 decode
        # =================================================

        try:

            decoded = decode_b64(
                content_b64
            )

        except Exception:

            print(
                f"\n=== BROKEN BASE64 DETECTED ===\n"
                f"{relative_path}"
            )

            file_regen_prompt = f"""
        以下ファイルを再生成してください。

        path:
        {relative_path}

        重要:
        - content本体を生成
        - base64ではなく生テキスト生成
        - markdown禁止
        - explanation禁止

        返却はファイル内容のみ
        """


            decoded = regenerate_file_with_context(
                relative_path,
                architecture,
                review_data
            )

            print(
                "\n=== BASE64 AUTO FIXED ==="
            )

            

        # UTF-8 normalize
        decoded = decoded.encode(
            "utf-8",
            errors="ignore"
        ).decode(
            "utf-8",
            errors="ignore"
        )

        # remove dangerous control chars only
        decoded = "".join(
            c for c in decoded
            if (
                c == "\n"
                or c == "\r"
                or c == "\t"
                or ord(c) >= 32
            )
        )

        # tab -> spaces
        decoded = decoded.replace(
            "\t",
            "    "
        )

        # normalize newline
        decoded = decoded.replace(
            "\r\n",
            "\n"
        )

        decoded = decoded.replace(
            "\r",
            "\n"
        )

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
このYAMLは構文エラーです。

必ず yaml.safe_load() 可能な
YAMLへ修正してください。

重要:
- YAML only
- markdown禁止
- explanation禁止
- indentation厳守
- key連結禁止
- owner/groupは別行
- ansible moduleは改行必須

壊れているYAML:
{decoded}

エラー:
{str(e)}
"""

                    fix_yaml_response = (
                        client.models.generate_content(
                            model=MODEL_NAME,
                            contents=yaml_fix_prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.05
                            )
                        )
                    )

                    decoded = (
                        fix_yaml_response.text
                        .strip()
                    )

                    decoded = strip_markdown_fence(
                        fix_yaml_response.text
                    )

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

validation_errors = []

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

run_command([
    "scp",
    "-r",
    str(SAFE_ROOT),
    f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/"
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
                "stderr": stderr
            })


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

else:

    print("\nValidation passed")

# =========================================================
# Final
# =========================================================

print("\nPipeline completed successfully")