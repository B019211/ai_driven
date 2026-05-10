from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

import google.generativeai as genai
import os

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

# -----------------------------------
# Build Prompt
# -----------------------------------

prompt = f"""
# Architecture

{architecture}

# Rules

{rules}

# Task

# Task

現在の構成を分析して、
改善提案を出してください。

以下の形式で出力してください:

# Improvement
## Title
## Reason
## Priority
## Implementation

# Ansible Changes
# Directory Changes
# Risks
"""

# -----------------------------------
# Gemini Request
# -----------------------------------

response = model.generate_content(
    prompt
)

output = response.text

# -----------------------------------
# Save Log
# -----------------------------------

timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

log_path = Path(
    f"logs/ai_run_{timestamp}.md"
)

log_path.write_text(
    output,
    encoding="utf-8"
)

doc_path = Path(
    "generated/docs/improvement_proposal.md"
)

doc_path.write_text(
    output,
    encoding="utf-8"
)

# -----------------------------------
# Print
# -----------------------------------

print(output)

print(f"\nSaved: {log_path}")