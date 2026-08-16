from pathlib import Path
from datetime import datetime
import base64
import binascii
import json
import os
import re
import time
import subprocess

from difflib import get_close_matches
from typing import Any, Dict, List, Tuple, Optional, Set

from dotenv import load_dotenv
from openai import OpenAI
from json_repair import repair_json
from jsonschema import validate, ValidationError

from config import (
    BLOCKING_SEVERITIES,
    MAX_RETRY,
    MAX_VALIDATION_RETRY,
    PROJECT_ROOT,
    TASK_DIR,
    SAFE_ROOT,
    MODEL_NAME,
    PIPELINE_PHASE,
    ANSIBLE_CONTROL_NODE,
    EXECUTION_NODE,
    REMOTE_PROJECT_ROOT,
    ALLOWED_PATHS,
    APPLICATION_ALLOWED_PATHS,
    CATEGORY_TO_TARGET,
    TASK_SEQUENCE,
)

from utility  import (
    extract_json,
    sanitize_json_string,
    safe_json_loads,
    encode_b64,
    decode_b64,
    safe_write_file,
    log_text,
    run_command,
    run_remote_command,
    repair_yaml_text,
    strip_markdown_fence,
    repair_podman_yaml_content,
    plan_repair,
)

from validation import (
    validate_base64,
    semantic_yaml_check,
    validate_known_paths,
    validate_cross_file_consistency,
    validate_podman_playbook,
    run_validation,
    run_remote_validation,
)

from deploy import (
    deploy_pipeline,
    analyze_deploy_error,
    run_browser_validation,
    run_php_lint,
    collect_deploy_evidence,
    analyze_deploy_result,
)

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
    timeout=900,
)


# =========================================================
# Schema
# =========================================================

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        "commands": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "files", "commands", "risks"],
    "additionalProperties": False,
}


REVIEW_SCHEMA = {
  "type": "object",
  "properties": {
    "approved": {"type": "boolean"},
    "summary": {"type": "string"},
    "risks": {
        "type": "array",
        "items": {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string"},
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                        "fix": {"type": "string"},
                    },
                },
            ]
        },
    },
    "diagnosis": {
      "type": "object",
      "properties": {
        "category": {
          "type": "string",
          "enum": ["application", "deployment", "configuration", "infrastructure"]
        },
        "root_cause": {
          "type": "string"
        },
        "reason": {
          "type": "string"
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      },
      "required": ["category", "root_cause", "reason", "confidence"]
    }
  },
  "required": ["approved", "summary", "risks", "diagnosis"]
}



# =========================================================
# AI Client
# =========================================================

def regenerate_file(path: str) -> str:
    """単一ファイル再生成"""

    prompt = f"""
以下ファイルのみ生成してください。

path:
{path}

重要:
- ファイル内容のみ返却
- markdown禁止
- explanation禁止
"""

    if path.endswith(".php"):
        prompt_name = "php_engineer.txt"

    elif path.endswith((".yml", ".yaml", ".ini")):
        prompt_name = "architect.txt"

    else:
        prompt_name = "architect.txt"

    system_prompt = (
        PROJECT_ROOT / f"prompts/{prompt_name}"
    ).read_text(encoding="utf-8")

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=8192,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }
    )

    choice = response.choices[0]

    print(choice)

    text = choice.message.content or getattr(
        choice.message,
        "reasoning_content",
        None
    )

    if not text:
        if choice.finish_reason == "length":
            raise RuntimeError(
                "Generation reached max tokens"
            )
        raise RuntimeError(
            f"Model returned empty response. finish_reason={choice.finish_reason}"
        )

    return strip_markdown_fence(text).strip()


def regenerate_file_with_context(path: str, architecture: str, context_data: Dict[str, Any], rules: str, format_rules: str) -> str:
    print("=== REGENERATE START ===")
    print(path)

    target = SAFE_ROOT / path

    if target.exists():
        current_file = target.read_text(encoding="utf-8")
    else:
        current_file = ""

    error_summary = []
    for err in context_data["errors"]:
        text = json.dumps(err, ensure_ascii=False)
        if "Unsupported parameters" in text:
            error_summary.append("- Remove unsupported parameters.")
        if "timeout" in text:
            error_summary.append("- Delete timeout parameter.")
    error_summary = "\n".join(error_summary)

    prompt = f"""
Validation errors:
{json.dumps(context_data['errors'], indent=2, ensure_ascii=False)}

Validation summary:
{error_summary}

Validation stdout:
{context_data.get('stdout', '')}

Validation stderr:
{context_data.get('stderr', '')}

Available PHP files:
{json.dumps(context_data.get('available_php_files', []), indent=2, ensure_ascii=False)}

Deployment evidence:
{json.dumps(context_data.get('evidence', {}), indent=2, ensure_ascii=False)}

Diagnosis:
{json.dumps(context_data.get('diagnosis', {}), indent=2, ensure_ascii=False)}

Current file:
{current_file}
 Edit only this file.
 Do NOT rewrite the whole architecture.
 Preserve all unrelated lines.
 Modify only the minimum lines needed to fix the error.
 Return the complete corrected file.

Return only the complete corrected file content.

Rules:
- Output the entire file.
- Never output partial content.
- Never output JSON.
- Never output markdown fences.
- Never return JSON.
- Never return markdown fences.
- Preserve the original file structure.
- If the file is YAML, output complete valid YAML.

Additional rules for Podman:

- containers.podman.podman_pod state must be one of:
  started
  stopped
  restarted
  absent
  created

- Never use:
  state: present

- Output must use only valid Ansible module parameters.

- Do not invent unsupported parameters.

- Return the COMPLETE file.
"""

    print("Calling Ollama...")

    try:

        if path.endswith(".php"):
            prompt_name = "php_engineer.txt"

        elif path.endswith((".yml", ".yaml", ".ini")):
            prompt_name = "architect.txt"

        else:
            prompt_name = "architect.txt"

        system_prompt = (
            PROJECT_ROOT / f"prompts/{prompt_name}"
        ).read_text(encoding="utf-8")

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=8192,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
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

    result = strip_markdown_fence(content).strip()

    print("===== REGENERATE RETURN CHECK =====")
    print(type(result))
    print(result[:100])

    return result

def regenerate_file_only(path: str) -> str:
    prompt = f"""
path:
{path}

重要:
- ファイル本文のみ
- markdown禁止
- explanation禁止
- 修正対象以外の変更は禁止。
- 既存のimage名、container名、port、volume、environment値を変更しない。
- 不足しているAnsible構造のみ修正する。
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=8192,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }
    )

    content = response.choices[0].message.content

    if content is None:
        raise RuntimeError("Empty response from model")

    return strip_markdown_fence(content).strip()


# =========================================================
# Generate
# =========================================================

def load_context() -> Dict[str, Any]:
    print("\n===== LOAD CONTEXT =====")

    architecture = (PROJECT_ROOT / "context/architecture.md").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "context/system_rules.md").read_text(encoding="utf-8")
    format_rules = (PROJECT_ROOT / "context/output_format.md").read_text(encoding="utf-8")
    review_rules = (PROJECT_ROOT / "context/reviewer_rules.md").read_text(encoding="utf-8")
    reviewer_prompt = (PROJECT_ROOT / "prompts/reviewer.txt").read_text(encoding="utf-8")
    # task = (PROJECT_ROOT / "context/task.md").read_text(encoding="utf-8")

    print("Context loaded")
    return {
        "architecture": architecture,
        "rules": rules,
        "format_rules": format_rules,
        "review_rules": review_rules,
        "reviewer_prompt": reviewer_prompt,
        # "task": task,
    }

def load_task(task_name: str) -> str:
    path = TASK_DIR / task_name

    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    return path.read_text(encoding="utf-8")

def generate_initial_data(context: Dict[str, Any], task_name: str, task: str) -> Tuple[Dict[str, Any], str]:
    print("\n===== GENERATE PROMPT =====")
    task_type = Path(task_name).stem
    print(f"Task Type = {task_type}")

    prompt = f"""

Role:
You are an AI software architect responsible for generating the files required by the specified task.

Task Type:
{task_type}

Task:
{task}

Task Scope Rules:
- The Task above defines the scope of the requested deliverable.
- Generate only files explicitly required by the Task.
- Do not generate files belonging to another task type.
- Do not infer additional infrastructure or application components that are not required by the Task.
- When the Task explicitly prohibits a technology or file type, that prohibition takes precedence.
- The Architecture and Rules below provide project-wide constraints, but they must not expand the scope of the current Task.
    
Architecture:
{context['architecture']}

Rules:
{context['rules']}

Output Format:
{context['format_rules']}
"""

    print(f"Prompt length = {len(prompt):,} chars")

    system_prompt = (PROJECT_ROOT / "prompts/architect.txt").read_text(encoding="utf-8")

    print("\n===== GENERATE START =====")
    start = time.time()

    print("Calling Ollama...")

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=8192,
            extra_body={
                "num_predict": 8192,
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
        )
        print("Ollama returned")
    except Exception as e:
        print("Ollama call failed")
        raise RuntimeError(f"Failed to call Ollama: {e}")

    elapsed = time.time() - start
    print(f"Generate finished ({elapsed:.1f}s)")

    choice = response.choices[0]

    print(choice)

    raw_output = choice.message.content or getattr(choice.message, "reasoning_content", None)

    print("finish_reason =", response.choices[0].finish_reason)
    print(response.choices[0])
    print("content =", repr(raw_output))

    print("RAW LENGTH =", len(raw_output or ""))
    print("===== RAW TAIL =====")
    print((raw_output or "")[-2000:])
    print("====================")

    if not raw_output:
        if choice.finish_reason == "length":
            raise RuntimeError(
                "Generation reached max_tokens before producing output. Increase max_tokens or disable thinking mode."
            )
        raise RuntimeError("Model returned empty response.")

    json_text = extract_json(raw_output)
    json_text = sanitize_json_string(json_text)

    data = safe_json_loads(json_text)

    required_defaults = {
        "commands": [],
        "risks": [],
        "files": [],
        "summary": "",
    }

    for key, default in required_defaults.items():
        data.setdefault(key, default)

    try:
        validate(instance=data, schema=OUTPUT_SCHEMA)
    except ValidationError as e:
        print("\nSchema validation failed")
        print(e)

        regeneration_context = {
            "source": "schema",
            "errors": [str(e)],
        }
        target_file = "all"

        regenerated = regenerate_file_with_context(
            target_file,
            context["architecture"],
            regeneration_context,
            context["rules"],
            context["format_rules"],
        )

        data = safe_json_loads(regenerated)
        validate(instance=data, schema=OUTPUT_SCHEMA)

    if not isinstance(data, dict):
        raise RuntimeError("Generated result must be object")

    return data, raw_output


# =========================================================
# Review
# =========================================================

def review_loop(data: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    retry_count = 0

    while True:
        print("\n===== REVIEW =====")
        print(f"Attempt {retry_count + 1}")

        review_request = f"""
Generated JSON:

{json.dumps(data, ensure_ascii=False)}

Review it.
Return JSON only.
"""

        print(f"\n=== REVIEW ATTEMPT {retry_count + 1} ===")
        print("Review request...")
        start = time.time()

        review_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": context["reviewer_prompt"]},
                {"role": "user", "content": review_request},
            ],
            temperature=0.0,
            max_tokens=8192,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
        )

        print(f"Review finished ({time.time() - start:.1f}s)")

        review_raw = review_response.choices[0].message.content
        print("\n=== REVIEW RAW ===")
        print(review_raw)

        review_json = extract_json(review_raw)
        review_json = sanitize_json_string(review_json)
        review_data = safe_json_loads(review_json)

        try:
            validate(instance=review_data, schema=REVIEW_SCHEMA)
            # =====================================================
            # Diagnosis (optional)
            # =====================================================
            review_data.setdefault(
                "diagnosis",
                {
                    "category": "application",
                    "root_cause": "",
                    "reason": "",
                    "confidence": 0.0,
                },
            )            
        except ValidationError as e:
            raise RuntimeError(f"Review schema invalid:\n{e}")

        risks = review_data.get("risks", [])
        blocking = []

        for r in risks:
            if not isinstance(r, dict):
                blocking.append({"severity": "WARNING", "description": r})
                continue

            severity = r.get("severity")
            if severity in BLOCKING_SEVERITIES:
                blocking.append(r)

        if not blocking:
            print("\nReview passed")
            break

        if review_data.get("approved", True):
            print("\nReview approved with warnings")
            break

        retry_count += 1

        if retry_count >= MAX_RETRY:
            print("\nMax retry reached")
            print("Continue pipeline with warnings")
            break

        print("\nBlocking risks found")

        fix_prompt = f"""
Fix this JSON.

Current JSON:

{json.dumps(data, ensure_ascii=False)}

Errors:

{json.dumps(blocking, ensure_ascii=False)}

Return JSON only.
"""

        retry_temp = max(0.05, 0.3 - (retry_count * 0.1))

        fix_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": Path("prompts/fixer.txt").read_text(encoding="utf-8")},
                {"role": "user", "content": fix_prompt},
            ],
            temperature=retry_temp,
            max_tokens=8192,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
        )

        fix_raw = fix_response.choices[0].message.content
        print("\n=== FIX RAW ===")
        print(fix_raw)

        fixed_json = extract_json(fix_raw)
        fixed_json = sanitize_json_string(fixed_json)
        data = safe_json_loads(fixed_json)

        try:
            validate(instance=data, schema=OUTPUT_SCHEMA)
        except ValidationError as e:
            raise RuntimeError(f"Fixed JSON schema invalid:\n{e}")

        required_paths = {
            "ansible/playbook.yml",
            "ansible/inventory.ini",
            "src/index.php",
        }

        generated_paths = {f["path"] for f in data["files"]}
        missing = required_paths - generated_paths

        if missing:
            print(f"Missing files: {missing}")
            for path in missing:
                content = regenerate_file(path)
                data["files"].append({"path": path, "content": content})

    return data, review_data


# =========================================================
# Generate Files
# =========================================================

def generate_files(data: Dict[str, Any], allowed_paths: Optional[Set[str]] = None) -> Tuple[List[dict], Path, Path, Path]:
    validation_errors: List[dict] = []

    if allowed_paths is None:
        allowed_paths = ALLOWED_PATHS

    import shutil

    if SAFE_ROOT.exists():
        shutil.rmtree(SAFE_ROOT)

    SAFE_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"SAFE_ROOT = {SAFE_ROOT}")

    for file in data.get("files", []):
        try:
            import yaml

            relative_path = file.get("path")
            print(f"\n===== FILE ===== {relative_path}")

            if relative_path:
                relative_path = relative_path.strip()

            content = file.get("content")

            if not relative_path:
                print("Skip invalid path")
                continue

            if not content:
                print(f"Skip empty content: {relative_path}")
                continue

            if relative_path.endswith((".yml", ".yaml")):
                print("===== BEFORE REPAIR =====")
                print(content)
                content = repair_podman_yaml_content(content)
                print("===== AFTER REPAIR =====")
                print(content)

            if not content.strip():
                raise ValueError(f"Empty content file: {relative_path}")

            if relative_path not in allowed_paths:
                raise ValueError(f"Forbidden path: {relative_path}")

            if relative_path.endswith((".yml", ".yaml")):
                try:
                    parsed_yaml = yaml.safe_load(content)
                except yaml.YAMLError:
                    try:
                        content = repair_yaml_text(content)
                        parsed_yaml = yaml.safe_load(content)
                        print("\n=== YAML REPAIRED LOCALLY ===")
                    except yaml.YAMLError as e:
                        print("\n=== INVALID YAML BEFORE SAVE ===")
                        print(content)

                        yaml_fix_prompt = f"""Fix this YAML.

Return YAML only.

{content}

Error:
{e}
"""

                        fix_yaml_response = None
                        for attempt in range(3):
                            try:
                                fix_yaml_response = client.chat.completions.create(
                                    model=MODEL_NAME,
                                    messages=[
                                        {"role": "system", "content": Path("prompts/fixer.txt").read_text(encoding="utf-8")},
                                        {"role": "user", "content": yaml_fix_prompt},
                                    ],
                                    temperature=0.0,
                                    max_tokens=8192,
                                    extra_body={
                                        "chat_template_kwargs": {
                                            "enable_thinking": False
                                        }
                                    }
                                )
                            except Exception as e:
                                if "503" in str(e):
                                    print(f"[WARN] Gemini 503 retry={attempt + 1}/3")
                                    time.sleep(10)
                                    continue
                                raise

                        if fix_yaml_response is None:
                            raise RuntimeError("Gemini fix_yaml failed after 3 retries")

                        content = fix_yaml_response.choices[0].message.content
                        content = strip_markdown_fence(content)
                        content = re.sub(r"^```yaml\s*", "", content, flags=re.MULTILINE)
                        content = re.sub(r"^```\s*", "", content, flags=re.MULTILINE)
                        content = re.sub(r"\s*```$", "", content)
                        print("\n=== YAML AUTO FIXED ===")
                        print(content)
                        parsed_yaml = yaml.safe_load(content)

                        semantic_problems = semantic_yaml_check(parsed_yaml)
                        if semantic_problems:
                            print("\n=== SEMANTIC WARNINGS ===")
                            for p in semantic_problems:
                                print(p)

            if relative_path.endswith((".yml", ".yaml")):
                path_problems = validate_known_paths(content)
                for p in path_problems:
                    validation_errors.append({"type": "path_typo", "detail": p})

            print(f"Decoded size : {len(content)}")
            print(content[:300])
            safe_write_file(SAFE_ROOT, relative_path, content)
        except Exception as e:
            print(f"Failed writing {relative_path}")
            print(e)
            validation_errors.append({"type": "yaml_autofix_failed", "file": str(SAFE_ROOT / relative_path), "stderr": str(e)})
            continue

    inventory_file = SAFE_ROOT / "ansible/inventory.ini"
    playbook_file = SAFE_ROOT / "ansible/playbook.yml"
    php_file = SAFE_ROOT / "src/index.php"

    return validation_errors, inventory_file, playbook_file, php_file



# =========================================================
# Repair
# =========================================================

def extract_file_content_from_response(content: str) -> str:
    """JSON 形式で返された再生成レスポンスからファイル本文を抽出する。"""

    try:
        data = safe_json_loads(content)
    except Exception:
        return strip_markdown_fence(content).strip()

    files = data.get("files") if isinstance(data, dict) else None
    if isinstance(files, list):
        first_file = files[0]
        if isinstance(first_file, dict):
            file_content = first_file.get("content")
            if isinstance(file_content, str):
                return strip_markdown_fence(file_content).strip()

    return strip_markdown_fence(content).strip()


def postprocess_regenerated_file_content(content: str, target_file: str) -> str:
    """Apply extension-specific repair to regenerated file content."""
    if target_file.endswith((".yml", ".yaml")):
        return repair_podman_yaml_content(content)
    return content


def discover_php_files(root: Path) -> List[Path]:
    """Discover generated PHP files under SAFE_ROOT/src."""
    php_dir = root / "src"
    if not php_dir.exists():
        return []

    return sorted([p for p in php_dir.glob("*.php") if p.is_file()])


def analyze_browser_validation(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Browser Validation の結果を解析して問題を返す。"""

    issues: List[Dict[str, Any]] = []
    status = payload.get("status")
    body = payload.get("body") or ""
    headers = payload.get("headers") or {}

    if payload.get("success") is False:
        issues.append({
            "type": "browser_connection_error",
            "detail": payload.get("stderr", "Browser validation failed")
        })

    if isinstance(status, int) and status >= 400:
        issues.append({"type": "browser_status", "severity": "warning", "detail": f"HTTP status {status}"})

    body_text = body.lower()
    if isinstance(body, str) and ("fatal error" in body_text or "parse error" in body_text or "uncaught" in body_text):
        issues.append({"type": "browser_body", "severity": "warning", "detail": "Response body contains an error message"})

    content_type = headers.get("Content-Type") if isinstance(headers, dict) else None
    if isinstance(content_type, str) and "text/html" in content_type.lower() and not body.strip():
        issues.append({"type": "browser_empty", "severity": "warning", "detail": "HTML response body is empty"})

    return issues


def analyze_php_lint_result(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """PHP Lint の結果を解析して問題を返す。"""

    issues: List[Dict[str, Any]] = []
    exit_code = payload.get("exit_code")
    stdout = payload.get("stdout") or ""
    stderr = payload.get("stderr") or ""
    combined = f"{stdout}\n{stderr}".strip()

    if exit_code == 0:
        return issues

    if combined:
        issues.append({"type": "php_lint", "severity": "warning", "detail": combined})
    else:
        issues.append({"type": "php_lint", "severity": "warning", "detail": "PHP lint failed"})

    return issues


def collect_php_includes(path: Path) -> List[dict]:
    """Collect static PHP include/require expressions from a PHP file."""
    text = path.read_text(encoding="utf-8")
    includes: List[dict] = []

    pattern = re.compile(
        r"\b(require|require_once|include|include_once)\b\s*(?:\(\s*)?(?P<expr>[^;]+?)(?:\s*\))?\s*;",
        re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        include_type = match.group(1).lower()
        expression = match.group("expr").strip()
        include_entry = {
            "type": include_type,
            "expression": expression,
        }

        parsed_path = parse_php_include_expression(expression)
        if parsed_path is not None:
            include_entry["path"] = parsed_path

        includes.append(include_entry)

    return includes


def parse_php_include_expression(expression: str) -> Optional[str]:
    """静的に解釈できる PHP include/require のパスを抽出する。"""
    expr = expression.strip()

    simple_match = re.fullmatch(r"['\"](?P<path>[^'\"]+)['\"]", expr)
    if simple_match:
        return simple_match.group("path")

    dir_match = re.fullmatch(
        r"__DIR__\s*\.\s*['\"](?P<path>[^'\"]+)['\"]",
        expr,
    )
    if dir_match:
        path = dir_match.group("path")
        return path.lstrip("/")

    return None


def resolve_php_include_path(
    php_path: Path,
    include_expr: str,
    safe_root: Path,
) -> Optional[Path]:
    """Resolve a static PHP include path relative to SAFE_ROOT, or return None if unsupported."""
    referenced_path = parse_php_include_expression(include_expr)
    if referenced_path is None:
        return None

    if not referenced_path.endswith(".php"):
        return None

    candidate = Path(referenced_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (php_path.parent / referenced_path).resolve()

    return resolved


def validate_php_cross_files(
    php_files: List[Path],
    safe_root: Path,
) -> List[dict]:
    """Validate PHP include/require cross-file references under SAFE_ROOT."""
    errors: List[dict] = []
    safe_root_resolved = safe_root.resolve()

    for php_path in php_files:
        includes = collect_php_includes(php_path)
        for include in includes:
            expression = include["expression"]
            resolved = resolve_php_include_path(php_path, expression, safe_root)
            if resolved is None:
                continue

            if not resolved.is_relative_to(safe_root_resolved):
                errors.append({
                    "type": "php_include",
                    "file": str(php_path.relative_to(safe_root_resolved)).replace("\\", "/"),
                    "include_type": include["type"],
                    "expression": expression,
                    "reference": expression,
                    "message": "Referenced path is outside SAFE_ROOT and is not allowed",
                })
                continue

            if not resolved.exists():
                errors.append({
                    "type": "php_include",
                    "file": str(php_path.relative_to(safe_root_resolved)).replace("\\", "/"),
                    "include_type": include["type"],
                    "expression": expression,
                    "reference": str(resolved.relative_to(safe_root_resolved)).replace("\\", "/"),
                    "message": "Referenced PHP file does not exist",
                })

    return errors


def run_local_php_lint(php_path: Path) -> Dict[str, Any]:
    """ローカル環境で `php -l` を実行して構文チェックを行う。"""

    # Use run_command helper to execute local php -l
    cmd = ["php", "-l", str(php_path)]
    code, stdout, stderr = run_command(cmd)
    return {"success": code == 0, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}


def repair_validation_errors(
    validation_errors: List[dict],
    validation_stdout: str,
    validation_stderr: str,
    architecture: str,
    rules: str,
    format_rules: str,
    safe_root: Path,
    target_file_override: Optional[str] = None,
    available_php_files: Optional[List[str]] = None,
    deploy_evidence: Optional[dict] = None,
    deploy_diagnosis=None,
) -> None:

    # 同一ファイルは1回だけ修正
    target_files = set()

    for err in validation_errors:
        file_value = err.get("file")
        if target_file_override:
            override_path = Path(target_file_override)
            if override_path.is_absolute():
                try:
                    target_files.add(str(override_path.relative_to(safe_root.resolve())).replace("\\", "/"))
                except ValueError:
                    target_files.add(str(override_path))
            else:
                target_files.add(target_file_override.replace("\\", "/"))
        elif file_value:
            resolved_file = Path(file_value)
            if not resolved_file.is_absolute():
                resolved_file = (safe_root / file_value).resolve()
            try:
                target_files.add(str(resolved_file.relative_to(safe_root.resolve())).replace("\\", "/"))
            except ValueError:
                target_files.add("ansible/playbook.yml")
        else:
            target_files.add("ansible/playbook.yml")

    for target_file in target_files:
        print(f"[ERROR] {target_file}")
        print("BEFORE REGENERATE")

        regeneration_context = {
            "source": "validation",
            "errors": validation_errors,
            "stdout": validation_stdout,
            "stderr": validation_stderr,
            "available_php_files": available_php_files or [],
            "evidence": deploy_evidence,
            "diagnosis": deploy_diagnosis,
        }

        regenerated = regenerate_file_with_context(
            target_file,
            architecture,
            regeneration_context,
            rules,
            format_rules,
        )
        # regenerated = extract_file_content_from_response(regenerated)
        print("===== REGENERATE regenerate_file_with_context RETURN CHECK =====")
        print(type(regenerated))
        print(repr(regenerated[:100]) if regenerated else regenerated)

        if regenerated is None:
            raise RuntimeError(
                f"Regeneration returned None: {target_file}"
            )

        regenerated = postprocess_regenerated_file_content(regenerated, target_file)
        if regenerated is None:
            raise RuntimeError(
                f"Regeneration returned None: {target_file}"
            )

        print("===== REGENERATE postprocess_regenerated_file_content RETURN CHECK =====")
        print(type(regenerated))
        print(repr(regenerated[:100]) if regenerated else regenerated)
        
        safe_write_file(safe_root, target_file, regenerated)
        print("AFTER WRITE")
        print("===== FILE AFTER WRITE =====")
        print((safe_root / target_file).read_text(encoding="utf-8")[:600])

        print("Repair completed.")

def repair_publish_port(playbook_path):
    text = Path(playbook_path).read_text(encoding="utf-8")

    text = text.replace(
        "- 80:80",
        "- 8080:80"
    )

    Path(playbook_path).write_text(
        text,
        encoding="utf-8"
    )


def perform_deploy_cycle() -> Tuple[dict, dict, dict, bool]:
    """Run deploy_pipeline, collect evidence, analyze error, and return all outputs.

    Returns: (deploy_result, deploy_evidence, deploy_diagnosis, deploy_success)
    """
    deploy_result = deploy_pipeline()
    deploy_evidence = collect_deploy_evidence()
    deploy_diagnosis = analyze_deploy_error(deploy_result, deploy_evidence)
    deploy_success = bool(deploy_result.get("success"))
    return deploy_result, deploy_evidence, deploy_diagnosis, deploy_success

# =========================================================
# main()
# =========================================================

def run_infrastructure_pipeline(context: Dict[str, Any], task_name: str, task: str) -> None:
    deploy_evidence = {}
    deploy_diagnosis = {}

    data, raw_output = generate_initial_data(
        context,
        task_name,
        task,
    )

    data, review_data = review_loop(data, context)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_text(PROJECT_ROOT / f"logs/ai_run_{timestamp}.txt", raw_output or "")
    log_text(
        PROJECT_ROOT / f"generated/runtime/output_{timestamp}.json",
        json.dumps(data, indent=2, ensure_ascii=False),
    )
    log_text(
        PROJECT_ROOT / f"generated/runtime/review_{timestamp}.json",
        json.dumps(review_data, indent=2, ensure_ascii=False),
    )

    print("\nSaved logs")

    validation_errors, inventory_file, playbook_file, php_file = generate_files(data)

    print("\n=== VALIDATION ===")

    playbook_path = SAFE_ROOT / "ansible" / "playbook.yml"

    try:
        import yaml

        if not playbook_file.exists():
            validation_errors.append({"type": "missing_playbook", "file": str(playbook_file)})
        else:
            print("\n=== PLAYBOOK CONTENT ===")
            print(playbook_file.read_text(encoding="utf-8"))

            playbook_text = playbook_file.read_text(encoding="utf-8")
            print(repr(playbook_text))
            yaml.safe_load(playbook_file.read_text(encoding="utf-8"))
            print("YAML parse ok")

        if not inventory_file.exists():
            validation_errors.append({"type": "missing_inventory", "file": str(inventory_file)})
        else:
            inventory_text = inventory_file.read_text(encoding="utf-8")
            if "asbsvr" not in inventory_text or "rockey8" not in inventory_text:
                validation_errors.append({"type": "invalid_inventory", "file": str(inventory_file), "stderr": "Inventory format is invalid."})

        if not playbook_file.exists():
            validation_errors.append({"type": "missing_playbook", "file": str(playbook_file)})

        if not php_file.exists():
            validation_errors.append({"type": "missing_php", "file": str(php_file)})
    except Exception as e:
        validation_errors.append({"type": "yaml_parse", "file": str(playbook_file), "stderr": str(e)})

    validation_errors, stdout, stderr = run_validation(SAFE_ROOT, inventory_file, playbook_file, php_file)

    if validation_errors:
        print("\n=== VALIDATION FAILED ===")
        for err in validation_errors:
            print(json.dumps(err, indent=2, ensure_ascii=False))

    validation_success = False

    for attempt in range(MAX_VALIDATION_RETRY):
        print(f"\n===== VALIDATION ATTEMPT {attempt + 1} =====")
        validation_errors, stdout, stderr = run_validation(SAFE_ROOT, inventory_file, playbook_file, php_file)
        print("ERROR COUNT =", len(validation_errors))
        for e in validation_errors:
            print(e["type"])

        if not validation_errors:
            print(f"Validation success attempt={attempt + 1}")
            validation_success = True
            break

        if attempt >= 1:
            print("Validation repair failed twice. Stop.")
            break

        repair_validation_errors(
            validation_errors,
            stdout,
            stderr,
            context["architecture"],
            context["rules"],
            context["format_rules"],
            SAFE_ROOT,
        )

    # repair完了後に転送
    print(playbook_file.read_text())
    print("===== SCP TO ANSIBLE CONTROL NODE =====")
    run_command([
        "scp",
        "-r",
        str(SAFE_ROOT),
        f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
    ])

    print("===== REMOTE PLAYBOOK CHECK =====")
    result = run_remote_command(
        ANSIBLE_CONTROL_NODE,
        "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml"
    )
    if isinstance(result, dict):
        print(result.get("stdout", ""))
    else:
        print(result)

    # asbsvr側確認
    remote_errors, stdout, stderr = run_remote_validation()

    if remote_errors:
        print("Remote validation failed")
        for e in remote_errors:
            print(e)
        raise RuntimeError("Remote validation failed")

    deploy_success = False
    if validation_success:
        print("\nValidation passed")
        print(playbook_file.read_text())
        deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = perform_deploy_cycle()

    if deploy_success:
        for repair_attempt in range(2):
            print(f"\n===== BROWSER VALIDATION (attempt {repair_attempt + 1}) =====")
            browser_result = run_browser_validation()
            browser_issues = analyze_browser_validation(browser_result)
            print(json.dumps(browser_result, indent=2, ensure_ascii=False))
            print("Browser issues:", json.dumps(browser_issues, ensure_ascii=False))

            print("\n===== PHP LINT =====")
            lint_result = run_php_lint()
            lint_issues = analyze_php_lint_result(lint_result)
            print(json.dumps(lint_result, indent=2, ensure_ascii=False))
            print("PHP lint issues:", json.dumps(lint_issues, ensure_ascii=False))

            diagnosis = review_data.get("diagnosis", {})
            repair_target = plan_repair(
                diagnosis,
                browser_result,
                browser_issues,
                lint_result,
                lint_issues,
                deploy_result,
                deploy_diagnosis,
            )

            if not browser_issues and not lint_issues:
                break

            repair_target = "src/index.php"
            repair_validation_errors(
                [{"type": issue["type"], "file": "ansible/playbook.yml", "stderr": issue["detail"]} for issue in browser_issues + lint_issues],
                browser_result.get("stdout", "") + "\n" + lint_result.get("stdout", ""),
                browser_result.get("stderr", "") + "\n" + lint_result.get("stderr", ""),
                context["architecture"],
                context["rules"],
                context["format_rules"],
                SAFE_ROOT,
                target_file_override=repair_target,
                deploy_evidence=deploy_evidence,
                deploy_diagnosis=deploy_diagnosis
            )

            print("\n===== REDEPLOY AFTER REPAIR =====")
            deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = perform_deploy_cycle()
            if not deploy_success:
                break

    print("validation_success =", validation_success)
    print("deploy_success =", deploy_success)
    print(json.dumps(deploy_diagnosis, indent=2))

    if deploy_diagnosis and deploy_diagnosis["root_cause"] == "none":
        print("Pipeline completed successfully")
        return

    else:
        print("\n=== DEPLOY FAILED DIAGNOSIS ===")
        print(json.dumps(
            deploy_diagnosis,
            indent=2,
            ensure_ascii=False
        ))

        repair_target = deploy_diagnosis.get("repair_target")

        if repair_target:
            print(f"\n===== DEPLOY AUTO REPAIR ({repair_target}) =====")

            # If the error is privileged port binding, apply quick port fix.
            error_text = (
                deploy_result.get("stdout", "")
                + "\n"
                + deploy_result.get("stderr", "")
            )

            if "rootlessport cannot expose privileged port 80" in error_text:
                print("===== REPAIR PUBLISH PORT =====")
                repair_publish_port(SAFE_ROOT / "ansible/playbook.yml")

            else:
                # Use deploy_diagnosis to regenerate the indicated repair_target
                try:
                    print(f"===== REGENERATE {repair_target} USING AI =====")
                    regeneration_context = {
                        "source": "deploy",
                        "errors": [deploy_diagnosis],
                        "stdout": deploy_result.get("stdout", ""),
                        "stderr": deploy_result.get("stderr", ""),
                        "evidence": deploy_evidence,
                        "diagnosis": deploy_diagnosis,
                    }

                    regenerated = regenerate_file_with_context(
                        repair_target,
                        context["architecture"],
                        regeneration_context,
                        context["rules"],
                        context["format_rules"],
                    )

                    if regenerated is None:
                        raise RuntimeError(f"Regeneration returned None: {repair_target}")

                    if repair_target.endswith((".yml", ".yaml")):
                        regenerated = repair_podman_yaml_content(regenerated)

                    safe_write_file(SAFE_ROOT, repair_target, regenerated)
                    print(f"Regenerated file written to SAFE_ROOT: {repair_target}")

                except Exception as e:
                    print("Auto-repair regeneration failed:", e)
                    # If regeneration fails, propagate as unknown deploy error
                    raise RuntimeError(f"Unknown deploy error.\n{deploy_result['stderr']}")

            print("\n===== SCP TO ANSIBLE CONTROL NODE =====")
            run_command([
                "scp",
                "-r",
                str(SAFE_ROOT),
                f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
            ])

            print("===== REMOTE PLAYBOOK CHECK =====")
            print(run_remote_command(
                ANSIBLE_CONTROL_NODE,
                "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml"
            ))

            # playbookが修正されたので古いPodを破棄
            print("\n===== REMOVE OLD POD =====")
            run_remote_command(
                EXECUTION_NODE,
                "podman pod rm -f lamp-pod || true"
            )

            print("\n===== REDEPLOY AFTER DEPLOY REPAIR =====")

            deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = perform_deploy_cycle()

            print("===== PODMAN STATUS AFTER DEPLOY =====")

            print(run_remote_command(
                EXECUTION_NODE,
                "podman ps -a"
            ))

            print(run_remote_command(
                EXECUTION_NODE,
                "podman pod ps"
            ))

            print(run_remote_command(
                EXECUTION_NODE,
                "podman logs php"
            ))

            print(run_remote_command(
                EXECUTION_NODE,
                "podman logs mysql"
            ))

            print("validation_success =", validation_success)
            print("deploy_success =", deploy_success)
            print(json.dumps(deploy_diagnosis, indent=2))
            
            if deploy_diagnosis and deploy_diagnosis["root_cause"] == "none":
                print("Pipeline completed successfully")
                return

        # Certain diagnosed root causes should trigger an automatic
        # repair attempt instead of immediately raising an exception.
        root = deploy_diagnosis.get("root_cause")
        auto_repair_root_causes = {
            "browser_connection_error",
            "pod_not_running",
            "apache_not_running",
            "container_not_running",
            "playbook_error",
            "ansible_module_error",
        }

        if root in auto_repair_root_causes:
            print(f"\n===== AUTO-REPAIR TRIGGERED FOR: {root} =====")

            # Perform AI-driven repair of the diagnosed target (e.g. playbook)
            file_to_repair = (
                deploy_diagnosis.get("repair_target")
                or "ansible/playbook.yml"
)

            regeneration_context = {
                "source": "deploy",
                "errors": [deploy_diagnosis],
                "stdout": deploy_result.get("stdout", ""),
                "stderr": deploy_result.get("stderr", ""),
                "evidence": deploy_evidence,
                "diagnosis": deploy_diagnosis,
            }

            try:
                print(f"\n===== REGENERATE {file_to_repair} USING AI (auto-repair) =====")
                regenerated = regenerate_file_with_context(
                    file_to_repair,
                    context["architecture"],
                    regeneration_context,
                    context["rules"],
                    context["format_rules"],
                )

                if regenerated is None:
                    raise RuntimeError(f"Regeneration returned None: {file_to_repair}")

                if file_to_repair.endswith((".yml", ".yaml")):
                    regenerated = repair_podman_yaml_content(regenerated)

                safe_write_file(SAFE_ROOT, file_to_repair, regenerated)
                print("Regenerated file written to SAFE_ROOT:", file_to_repair)

            except Exception as e:
                raise RuntimeError(
                    f"Deploy auto repair failed while regenerating "
                    f"{repair_target}: {e}"
                ) from e
                # Fall back to previous behavior (attempt redeploy without regen)

            # Transfer repaired files to control node and redeploy
            print("\n===== SCP TO ANSIBLE CONTROL NODE (auto-repair) =====")
            run_command([
                "scp",
                "-r",
                str(SAFE_ROOT),
                f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
            ])

            print("===== REMOTE PLAYBOOK CHECK (auto-repair) =====")
            print(run_remote_command(
                ANSIBLE_CONTROL_NODE,
                "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml"
            ))

            print("\n===== REMOVE OLD POD (auto-repair) =====")
            run_remote_command(
                EXECUTION_NODE,
                "podman pod rm -f lamp-pod || true"
            )

            print("\n===== REDEPLOY AFTER AUTO-REPAIR =====")
            deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = perform_deploy_cycle()
            
            print("===== AUTO-REPAIR DIAGNOSIS =====")
            print(json.dumps(deploy_diagnosis, indent=2, ensure_ascii=False))

            if deploy_diagnosis.get("root_cause") == "none":
                print("Pipeline completed successfully after auto-repair")
                return

        raise RuntimeError("Deploy failed")

def review_application(
    data: Dict[str, Any],
    task_name: str,
    task: str,
    rules: str,
) -> Dict[str, Any]:

    print("\n===== APPLICATION REVIEW START =====")

    review_prompt = f"""
Role:
You are an application reviewer for an AI-driven CI/CD pipeline.

Task Name:
{task_name}

Task:
{task}

Project Rules:
{rules}

Review the generated files against the Task and Project Rules.

Review priority:

1. Scope compliance
   - Generate only files required by the Task.
   - Reject files that belong to infrastructure when the Task prohibits infrastructure files.
   - Reject Ansible or Podman files when the Task prohibits them.
   - Reject database-related files or configuration when the Task prohibits MySQL.

2. Requirement compliance
   - Verify that required files are present.
   - Verify that the generated files satisfy the explicit requirements in the Task.

3. PHP correctness
   - PHP syntax issues
   - Undefined variables
   - Basic error handling issues

4. Security
   - Security risks relevant to the generated application.

5. Code quality
   - Only identify issues that materially affect the requested application.

Do not reject a generated file based only on generic best practices when that issue is outside the scope of the current Task.

Do not invent requirements that are not present in the Task or Project Rules.

Generated Files:
{json.dumps(data.get("files", []), indent=2, ensure_ascii=False)}

Return JSON:

{{
    "approved": true/false,
    "issues": [],
    "summary": "",
    "risks": []
}}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are an expert PHP reviewer."
            },
            {
                "role": "user",
                "content": review_prompt,
            },
        ],
        temperature=0.0,
    )

    raw = response.choices[0].message.content

    review_result = safe_json_loads(
        sanitize_json_string(
            extract_json(raw)
        )
    )

    print("\n===== APPLICATION REVIEW RESULT =====")
    print(json.dumps(
        review_result,
        indent=2,
        ensure_ascii=False
    ))

    return review_result

def run_application_pipeline(
    context: Dict[str, Any],
    task_name: str,
    task: str,
) -> None:

    print("\n===== APPLICATION PIPELINE START =====")

    data, raw_output = generate_initial_data(
        context,
        task_name,
        task,
    )

    print("\n===== APPLICATION REVIEW START =====")
    review_result = review_application(data, task_name, task, context.get("rules", ""))
    if not review_result.get("approved", False):
        print("Application review failed.")
        return
    print("\n===== APPLICATION REVIEW END =====")

    print("\n===== APPLICATION GENERATE COMPLETE =====")

    print("Generated files:")
    for file in data.get("files", []):
        print("-", file.get("path"))

    # Persist generated files to SAFE_ROOT so we can validate them locally.
    validation_errors, inventory_file, playbook_file, php_file = generate_files(
        data,
        allowed_paths=ALLOWED_PATHS | APPLICATION_ALLOWED_PATHS,
    )

    php_files = discover_php_files(SAFE_ROOT)
    if not php_files and php_file.exists():
        php_files = [php_file]

    print("\n===== PHP VALIDATION (local) =====")

    validation_success = False

    for attempt in range(MAX_VALIDATION_RETRY):
        print(f"\n===== PHP VALIDATION ATTEMPT {attempt + 1} =====")

        php_files = discover_php_files(SAFE_ROOT)
        if not php_files and php_file.exists():
            php_files = [php_file]

        validation_errors = []
        for php_path in php_files:
            lint_result = run_local_php_lint(php_path)
            lint_issues = analyze_php_lint_result(lint_result)

            if lint_issues:
                print(f"PHP lint issues for {php_path}:", json.dumps(lint_issues, ensure_ascii=False))
                validation_errors.append({
                    "type": "php_lint",
                    "file": str(php_path.relative_to(SAFE_ROOT)).replace("\\", "/"),
                    "stdout": lint_result.get("stdout", ""),
                    "stderr": lint_result.get("stderr", ""),
                })
            else:
                print(f"PHP validation passed for {php_path}")

        if not validation_errors:
            cross_file_errors = validate_php_cross_files(php_files, SAFE_ROOT)
            if cross_file_errors:
                print("PHP validation passed")
                print("Cross-file validation failed")
                for err in cross_file_errors:
                    print(json.dumps(err, ensure_ascii=False))

                if attempt >= MAX_VALIDATION_RETRY - 1:
                    print("Cross-file repair failed. Stop.")
                    break

                available_files = [str(p.relative_to(SAFE_ROOT)).replace("\\", "/") for p in php_files]
                repair_validation_errors(
                    cross_file_errors,
                    "",
                    "",
                    context["architecture"],
                    context["rules"],
                    context["format_rules"],
                    SAFE_ROOT,
                    available_php_files=available_files,
                )
                continue

            print("PHP validation passed")
            validation_success = True
            break

        if attempt >= MAX_VALIDATION_RETRY - 1:
            print("PHP repair failed. Stop.")
            break

        # Repair only failed PHP files
        repair_validation_errors(
            validation_errors,
            "\n".join(err.get("stdout", "") for err in validation_errors),
            "\n".join(err.get("stderr", "") for err in validation_errors),
            context["architecture"],
            context["rules"],
            context["format_rules"],
            SAFE_ROOT,
        )

    print("validation_success =", validation_success)

    # =========================================================
    # Deploy（Infrastructure の既存機構を再利用）
    # - SAFE_ROOT を Ansible Control Node に転送
    # - リモート検証（syntax-check）を行い、問題なければ deploy を実行
    # - デプロイ後に Browser Validation / PHP Lint を実行
    # Minimal change: re-use existing infra functions and commands.
    print("\n===== APPLICATION PIPELINE DEPLOY SEQUENCE START =====")

    if validation_success:
        print("===== SCP TO ANSIBLE CONTROL NODE =====")
        run_command([
            "scp",
            "-r",
            str(SAFE_ROOT),
            f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
        ])

        print("===== REMOTE PLAYBOOK CHECK =====")
        try:
            remote_cat = run_remote_command(
                ANSIBLE_CONTROL_NODE,
                "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml",
            )
            print(remote_cat if isinstance(remote_cat, str) else remote_cat)
        except Exception as e:
            print("Remote playbook check failed:", e)

        print("===== REMOTE VALIDATION =====")
        try:
            remote_errors, rv_stdout, rv_stderr = run_remote_validation()
            if remote_errors:
                print("Remote validation reported errors:")
                for e in remote_errors:
                    print(e)
        except Exception as e:
            print("Remote validation failed:", e)

        print("===== PERFORM DEPLOY CYCLE =====")
        try:
            deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = perform_deploy_cycle()
            print("deploy_success =", deploy_success)
            print(json.dumps(deploy_diagnosis, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Deploy failed:", e)
            deploy_result = {}
            deploy_evidence = {}
            deploy_diagnosis = {}
            deploy_success = False

        print("\n===== BROWSER VALIDATION (application pipeline) =====")
        try:
            browser_result = run_browser_validation()
            print(json.dumps(browser_result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Browser validation failed:", e)

        print("\n===== PHP LINT (application pipeline) =====")
        try:
            lint_result = run_php_lint()
            print(json.dumps(lint_result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("PHP lint (remote) failed:", e)

    else:
        print("Skipping deploy: PHP validation did not succeed.")

    print("\n===== APPLICATION PIPELINE END =====")

def main() -> None:
    context = load_context()

    task_handlers = {
        "infrastructure": run_infrastructure_pipeline,
        "application": run_application_pipeline,
    }

    for task_name in TASK_SEQUENCE:
        task = load_task(task_name)
        task_type = Path(task_name).stem
        handler = task_handlers.get(task_type)

        if handler is None:
            print(f"\n===== SKIP TASK: {task_name} (not implemented) =====")
            continue

        print(f"\n===== RUN TASK: {task_name} =====")
        handler(context, task_name, task)


if __name__ == "__main__":
    main()
