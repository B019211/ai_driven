from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

import google.generativeai as genai
import os
import json
import re
import time

BLOCKING_SEVERITIES = ["BLOCKER", "HIGH"]

# -----------------------------------
# Utility
# -----------------------------------


def extract_json(text: str) -> str:
    """
    AIレスポンスからJSON部分だけ抽出
    object / array 両対応
    """

    text = text.strip()

    # markdown fence除去
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    text = text.strip()

    # object or array の先頭検出
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

# -----------------------------------
# Load ENV
# -----------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found")

# -----------------------------------
# Gemini Setup
# -----------------------------------

genai.configure(api_key=api_key)

generator_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "temperature": 0.7
    },
    system_instruction="""
あなたは熟練のソフトウェアエンジニアです。

要件を満たす実装を生成してください。

重要:
- JSONのみ返却
- 説明文禁止
- 本番運用を意識
"""
)

reviewer_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "temperature": 0.1
    },
    system_instruction="""
あなたは非常に厳格な
DevSecOps reviewerです。

重点:
- secrets
- 本番リスク
- 権限
- hardcoded password
- destructive operation
- 保守性

曖昧ならrejectしてください。
"""
)

fix_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "temperature": 0.2
    },
    system_instruction="""
あなたは修正専門AIです。

既存コードを壊さず、
最小修正を行ってください。

全面再生成は禁止です。
"""
)

# -----------------------------------
# Load Context
# -----------------------------------

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

# -----------------------------------
# Build Prompt
# -----------------------------------

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

IMPORTANT:
Return JSON only.
Do not use markdown.
Do not explain anything.
Do not wrap with ```json
"""

# -----------------------------------
# Gemini Request
# -----------------------------------

response = generator_model.generate_content(
    prompt
)

output = response.text

print(output)

# -----------------------------------
# JSON Parse
# -----------------------------------

json_text = extract_json(output)

try:
    data = json.loads(json_text)

except json.JSONDecodeError as e:

    print("\nJSON Parse Error")
    print(e)

    repair_prompt = f"""
以下のJSONは壊れています。

JSONとして修復してください。

重要:
- 意味を変えない
- JSONのみ返却
- markdown禁止

Broken JSON:
{json_text}
"""

    repair_response = fix_model.generate_content(
        repair_prompt
    )

    repaired_json = extract_json(
        repair_response.text
    )

    data = json.loads(repaired_json)

# -----------------------------------
# Reviewer Phase
# -----------------------------------

review_request = f"""
# Review Rules

{review_rules}

# Reviewer Prompt

{reviewer_prompt}

# Generated Output

{json.dumps(data, indent=2, ensure_ascii=False)}

Review this output.
"""

for i in range(5):

    try:

        print(
            f"\nReview request attempt: {i + 1}"
        )

        review_response = reviewer_model.generate_content(
            review_request
        )

        break

    except Exception as e:

        print(e)

        if i == 4:
            raise

        print(
            "\nWaiting for API cooldown..."
        )

        time.sleep(45)

review_output = review_response.text

print("\n=== REVIEW RESULT ===")
print(review_output)

review_json = extract_json(review_output)

review_data = json.loads(review_json)

# -----------------------------------
# Review Gate
# -----------------------------------

MAX_RETRY = 3
retry_count = 0

while True:

    risks = review_data.get("risks", [])

    blocking_risks = []

    for r in risks:

        # dict以外は無視
        if not isinstance(r, dict):
            continue

        severity = r.get("severity")

        if severity in BLOCKING_SEVERITIES:
            blocking_risks.append(r)

    # blocker/high が無ければ通す
    if len(blocking_risks) == 0:
        print("Only warning-level risks found")
        print("Accepting result")
        break

    print("Review failed")
    print("Retrying with fixes...")

    retry_count += 1

    if retry_count >= MAX_RETRY:
        print("Max retry reached")
        exit(1)

    # Reviewer結果をGeneratorへ返す
    fix_prompt = f"""
    前回のJSONを修正してください。

    重要:
    - 元のJSON構造を維持
    - summary/files/commands/risks を必ず含める
    - files配列を部分返却しない
    - 完全なJSON objectを返す
    - JSON array単体は禁止
    - markdown禁止

    前回JSON:
    {json.dumps(data, ensure_ascii=False, indent=2)}

    レビュー結果:
    {json.dumps(review_data, ensure_ascii=False, indent=2)}
    """
    
    retry_temp = max(
        0.05,
        0.3 - (retry_count * 0.1)
    )

    fix_model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={
            "temperature": retry_temp
        },
        system_instruction="""
あなたは修正専門AIです。

既存コードを壊さず、
必要最小限の修正のみ行ってください。

全面再生成は禁止です。
"""
    )

    fix_response = fix_model.generate_content(
        fix_prompt
    )

    print("\n=== FIX RESULT ===\n")
    print(fix_response.text)

    raw_text = fix_response.text

    print("\n=== RAW AI RESPONSE ===")
    print(raw_text)

    result_json = extract_json(raw_text)

    print("\n=== EXTRACTED JSON ===")
    print(result_json)

    result = json.loads(result_json)
    if not isinstance(result, dict):
        raise ValueError(
            "AI response must be JSON object"
        )

    # 再レビュー
    review_request = f"""
You are a strict DevSecOps reviewer.

Review this generated result.

Rules:
- No secrets exposure
- No destructive operations
- Persistent volume必須
- PHP only, No framework
- PDO mandatory
- No hardcoded password
- Production riskチェック

Return JSON:
{{
  "approved": true/false,
  "risks": [],
  "fixes": [],
  "summary": ""
}}

Target:
{json.dumps(result, ensure_ascii=False, indent=2)}
"""

    review_response = reviewer_model.generate_content(
        review_request
    )

    print("\n=== RE-REVIEW RESULT ===\n")
    print(review_response.text)

    review_json = extract_json(review_response.text)

    review_data = json.loads(review_json)

    data = result

# -----------------------------------
# Save Log
# -----------------------------------

timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

log_path = Path(
    f"logs/ai_run_{timestamp}.md"
)

log_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

log_path.write_text(
    output,
    encoding="utf-8"
)

# -----------------------------------
# Save Docs
# -----------------------------------

doc_path = Path(
    "generated/docs/improvement_proposal.md"
)

doc_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

doc_path.write_text(
    output,
    encoding="utf-8"
)

# -----------------------------------
# Save JSON
# -----------------------------------

json_path = Path(
    f"generated/runtime/output_{timestamp}.json"
)

json_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

json_path.write_text(
    json.dumps(data, indent=2),
    encoding="utf-8"
)

# -----------------------------------
# Print Result
# -----------------------------------

print(f"\nSaved: {log_path}")
print(f"Saved: {json_path}")

# -----------------------------------
# Save Review JSON
# -----------------------------------

review_path = Path(
    f"generated/runtime/review_{timestamp}.json"
)

review_path.write_text(
    json.dumps(
        review_data,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

print(f"Saved: {review_path}")

# -----------------------------------
# Generate Files
# -----------------------------------

safe_root = Path(
    "generated/files"
)

for file in data.get("files", []):

    relative_path = (
        file.get("path")
        or file.get("file")
    )

    if not relative_path:
        print("skip:", file)
        continue

    file_path = safe_root / relative_path

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path.write_text(
        file["content"],
        encoding="utf-8"
    )

    print(f"Generated: {file_path}")