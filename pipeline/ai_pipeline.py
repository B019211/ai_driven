from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

import google.generativeai as genai
import os
import json
import re
import time

# -----------------------------------
# Utility
# -----------------------------------

def extract_json(text):

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL
    )

    if not match:
        raise ValueError(
            "JSON not found in response"
        )

    return match.group(0)

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

model = genai.GenerativeModel(
    "gemini-2.5-flash"
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

response = model.generate_content(
    prompt
)

output = response.text

print(output)

# -----------------------------------
# JSON Parse
# -----------------------------------

json_text = extract_json(output)

data = json.loads(json_text)

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

print("\nWaiting for API cooldown...")

time.sleep(45)

review_response = model.generate_content(
    review_request
)

review_output = review_response.text

print("\n=== REVIEW RESULT ===")
print(review_output)

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
# Generate Files
# -----------------------------------

safe_root = Path(
    "generated/files"
)

for file in data.get("files", []):

    file_path = safe_root / file["path"]

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path.write_text(
        file["content"],
        encoding="utf-8"
    )

    print(f"Generated: {file_path}")