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


# =========================================================
# Constants
# =========================================================

BLOCKING_SEVERITIES = ["BLOCKER", "HIGH"]

MAX_RETRY = 3

SAFE_ROOT = Path("generated/files").resolve()

MODEL_NAME = "gemini-2.5-flash"


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
    return base64.b64decode(
        content.encode("utf-8")
    ).decode("utf-8")


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

現在の構成を改善してください。

以下をJSONで返してください:

- summary
- files
- commands
- risks

filesには生成すべきファイルを含めてください。

重要:
- contentはcontent_b64へbase64で格納
- markdown禁止
- JSON only
"""


# =========================================================
# Generate
# =========================================================

response = client.models.generate_content(
    model=MODEL_NAME,
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=OUTPUT_SCHEMA,
        system_instruction="""
あなたは熟練のソフトウェアエンジニアです。

要件を満たす実装を生成してください。

重要:
- JSON only
- markdown禁止
- 本番運用品質
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
あなたは厳格なDevSecOps reviewerです。

重点:
- secrets
- destructive operations
- hardcoded passwords
- 本番リスク
- 権限
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

    retry_count += 1

    if retry_count >= MAX_RETRY:
        raise RuntimeError(
            "Max retry reached"
        )

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
    raw_output
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


# =========================================================
# Generate Files
# =========================================================

SAFE_ROOT.mkdir(
    parents=True,
    exist_ok=True
)

for file in data.get("files", []):

    relative_path = file.get("path")

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

    try:

        decoded = decode_b64(
            content_b64
        )

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
# Final
# =========================================================

print("\nPipeline completed successfully")