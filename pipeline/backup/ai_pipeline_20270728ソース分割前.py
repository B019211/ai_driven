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
from typing import Any, Dict, List, Tuple, Optional

from dotenv import load_dotenv
from openai import OpenAI
from json_repair import repair_json
from jsonschema import validate, ValidationError


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

# =========================================================
# Utility
# =========================================================

def extract_json(text: Optional[str]) -> str:
    """AIレスポンスから JSON 部分のみ抽出して返す。"""

    text = (text or "").strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    obj_start = text.find("{")
    arr_start = text.find("[")

    candidates = [x for x in (obj_start, arr_start) if x != -1]
    if not candidates:
        raise ValueError("JSON start not found")

    start = min(candidates)
    end = text.rfind("}") if text[start] == "{" else text.rfind("]")

    return text[start:] if end == -1 else text[start : end + 1]


def sanitize_json_string(text: str) -> str:
    """JSON の不正なバックスラッシュをエスケープして返す。"""

    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)


def safe_json_loads(text: str) -> Dict[str, Any]:
    """壊れた JSON を修復して dict を返す。修復できなければ例外を投げる。"""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = sanitize_json_string(repair_json(text))
        print("\n=== REPAIRED JSON ===")
        print(repaired[:1500])
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
            (PROJECT_ROOT / "logs/broken_json.txt").write_text(repaired, encoding="utf-8")
            raise RuntimeError(f"JSON repair failed: {e}")


def encode_b64(content: str) -> str:
    """UTF-8 でエンコードした文字列を base64 文字列で返す。"""

    return base64.b64encode(content.encode("utf-8")).decode("utf-8")


def decode_b64(content: str) -> str:
    """base64 文字列をデコードして UTF-8 文字列で返す。"""

    content = content.strip().replace("\n", "").replace("\r", "")
    missing_padding = len(content) % 4
    if missing_padding:
        content += "=" * (4 - missing_padding)
    try:
        raw = base64.b64decode(content, validate=False)
        return raw.decode("utf-8", errors="replace")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid base64 content: {e}")


def safe_write_file(root: Path, relative_path: str, content: str) -> None:
    """Path-traversal を防いでファイルを書き込む。"""

    resolved = (root / relative_path).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"Path traversal detected: {relative_path}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    print(f"Generated: {resolved}")


def log_text(path: Path, text: str) -> None:
    """指定パスへテキストログを書き込む（ディレクトリを自動作成）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(command: List[str]) -> Tuple[int, str, str]:
    """外部コマンドを実行して (returncode, stdout, stderr) を返す。"""

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as e:
        return 999, "", str(e)


def run_remote_command(host: str, remote_command: str) -> Tuple[int, str, str]:
    """SSH 経由でリモートコマンドを実行するラッパー。"""

    return run_command(["ssh", "-o", "BatchMode=yes", host, remote_command])


def repair_yaml_text(text: str) -> str:
    """軽微な YAML 破損を修復する。"""

    text = re.sub(r"\{\{\s*([^\}]+)\s*\}\}", r"{{ \1 }}", text)
    text = re.sub(r"([^\n])(\s+[A-Za-z_][A-Za-z0-9_]*:)", r"\1\n\2", text)
    text = re.sub(r"(- name:[^\n]+)\s+([a-zA-Z0-9_.]+:)", r"\1\n  \2", text)
    text = re.sub(r"([^\n])(group:)", r"\1\n\2", text)
    text = re.sub(r'"{{\s*([^}]+)\s*}}([^"\n]*)', r'"{{ \1 }}\2"', text)
    return text


def strip_markdown_fence(text: Optional[str]) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def repair_podman_yaml_content(content: str) -> str:
    """Podman/Ansible の生成誤りを自動修復する。"""

    try:
        import yaml

        parsed = yaml.safe_load(content)
    except Exception:
        return content

    if not isinstance(parsed, (list, dict)):
        return content

    pod_publish_ports: List[str] = []
    pod_configs: List[dict] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key == "containers.podman.podman_container" and isinstance(value, dict):
                    publish_values = []
                    for field_name in ("ports", "publish"):
                        field_value = value.pop(field_name, None)
                        if field_value:
                            if isinstance(field_value, list):
                                for item in field_value:
                                    if isinstance(item, str):
                                        publish_values.append(item)
                                    elif isinstance(item, dict):
                                        for inner_key, inner_value in item.items():
                                            if isinstance(inner_value, str):
                                                publish_values.append(f"{inner_key}:{inner_value}")
                            elif isinstance(field_value, str):
                                publish_values.append(field_value)

                    if publish_values:
                        pod_publish_ports.extend(publish_values)

                    if "environment" in value and "env" not in value:
                        value["env"] = value.pop("environment")

                    env_value = value.get("env")
                    if isinstance(env_value, list):
                        normalized_env = {}
                        for item in env_value:
                            if isinstance(item, str):
                                if "=" in item:
                                    key, env_value_part = item.split("=", 1)
                                    normalized_env[key] = env_value_part
                                else:
                                    normalized_env[item] = ""
                            elif isinstance(item, dict):
                                for env_key, env_val in item.items():
                                    if isinstance(env_key, str) and isinstance(env_val, str):
                                        normalized_env[env_key] = env_val
                        if normalized_env:
                            value["env"] = normalized_env

                elif key == "containers.podman.podman_pod" and isinstance(value, dict):
                    pod_configs.append(value)

                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(parsed)

    for pod_config in pod_configs:
        if pod_publish_ports:
            existing_publish = pod_config.get("publish") or []
            if isinstance(existing_publish, list):
                merged_publish = list(existing_publish)
            else:
                merged_publish = [existing_publish]
            for port in pod_publish_ports:
                if port not in merged_publish:
                    merged_publish.append(port)
            pod_config["publish"] = merged_publish

    return yaml.safe_dump(parsed, sort_keys=False, default_flow_style=False)

def plan_repair(
    diagnosis,
    browser_result,
    browser_issues,
    lint_result,
    lint_issues,
    deploy_result,
):
    # Reviewer診断を優先
    category = diagnosis.get("category")

    target = CATEGORY_TO_TARGET.get(category)

    if target is not None:
        return target

    # AIが判断できなかった場合だけPythonが補完
    if browser_issues:
        return "ansible/playbook.yml"

    if lint_issues:
        return "src/index.php"

    return None

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

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": (PROJECT_ROOT / "prompts/php_engineer.txt").read_text(encoding="utf-8")},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=8192,
    )

    text = response.choices[0].message.content

    if not text:
        raise RuntimeError(f"Empty response for {path}")

    return strip_markdown_fence(text).strip()


def regenerate_file_with_context(path: str, architecture: str, context_data: Dict[str, Any], rules: str, format_rules: str) -> str:
    print("=== REGENERATE START ===")
    print(path)

    current_file = (SAFE_ROOT / path).read_text(encoding="utf-8")

    validation_log = "\n".join(
        err.get("stdout", "") + "\n" + err.get("stderr", "")
        for err in context_data["errors"]
    )

    error_summary = []
    for err in context_data["errors"]:
        text = err.get("stdout", "") + "\n" + err.get("stderr", "")
        if "Unsupported parameters" in text:
            error_summary.append("- Remove unsupported parameters.")
        if "timeout" in text:
            error_summary.append("- Delete timeout parameter.")
    error_summary = "\n".join(error_summary)

    prompt = f"""
Validation errors:
{json.dumps(context_data['errors'], indent=2, ensure_ascii=False)}

Required fixes:
{error_summary}

Validation log:
{validation_log}

Stdout:
{context_data.get('stdout', '')}

Stderr:
{context_data.get('stderr', '')}

Target file:
{path}

Current file:
{current_file}

Architecture:
{architecture}

Rules:
{rules}

Output format:
{format_rules}

Return only the corrected file content.
Do not return JSON or explanation.
"""

    print("Calling Ollama...")

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": (PROJECT_ROOT / "prompts/php_engineer.txt").read_text(encoding="utf-8")},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
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
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
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
    task = (PROJECT_ROOT / "context/task.md").read_text(encoding="utf-8")

    print("Context loaded")
    return {
        "architecture": architecture,
        "rules": rules,
        "format_rules": format_rules,
        "review_rules": review_rules,
        "reviewer_prompt": reviewer_prompt,
        "task": task,
    }


def generate_initial_data(context: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    print("\n===== GENERATE PROMPT =====")

    prompt = f"""
Architecture:
{context['architecture']}

Rules:
{context['rules']}

Output Format:
{context['format_rules']}

Task:
{context['task']}
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

        regeneration_context = {"source": "schema", "errors": [str(e)]}
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

def generate_files(data: Dict[str, Any]) -> Tuple[List[dict], Path, Path, Path]:
    validation_errors: List[dict] = []

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

            if relative_path not in ALLOWED_PATHS:
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
# Validation
# =========================================================

def validate_base64(data: str) -> bool:
    if not data:
        return False
    data = data.strip()
    if not re.match(r"^[A-Za-z0-9+/=\r\n]+$", data):
        return False
    try:
        base64.b64decode(data, validate=True)
        return True
    except Exception:
        return False


def semantic_yaml_check(obj: Any) -> List[str]:
    problems: List[str] = []
    known_yaml_keys = {
        "pod_name",
        "mysql_container_name",
        "web_container_name",
        "mysql_root_password",
        "mysql_image",
        "web_image",
        "html_dir",
        "web_port",
        "mysql_db",
    }

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                matches = get_close_matches(k, known_yaml_keys, n=1, cutoff=0.80)
                if matches and k != matches[0]:
                    problems.append(f"Possible typo: {k} -> {matches[0]}")
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return problems


def validate_known_paths(text: str) -> List[str]:
    problems = []
    known_paths = [
        "/home/vboxuser/containers/html",
        "/home/vboxuser/containers/html/index.php",
        "/home/vboxuser/containers/mysql",
    ]
    path_pattern = r"/home/[^\s\"']+"
    paths = re.findall(path_pattern, text)

    for p in paths:
        match = get_close_matches(p, known_paths, n=1, cutoff=0.85)
        if match and p != match[0]:
            problems.append(f"Possible path typo: {p} -> {match[0]}")

    return problems


def validate_cross_file_consistency(playbook_file: Path, php_file: Path) -> List[dict]:
    errors: List[dict] = []
    if not playbook_file.exists() or not php_file.exists():
        return errors

    playbook_text = playbook_file.read_text(encoding="utf-8")
    php_text = php_file.read_text(encoding="utf-8")

    mysql_db = re.search(r"MYSQL_DATABASE=(\w+)", playbook_text)
    php_db = re.search(r'\$db\s*=\s*"([^"]+)"', php_text)

    if mysql_db and php_db and mysql_db.group(1) != php_db.group(1):
        errors.append({"type": "cross_file", "playbook_db": mysql_db.group(1), "php_db": php_db.group(1)})

    return errors


def validate_podman_playbook(playbook_file: Path) -> List[dict]:
    errors: List[dict] = []

    try:
        import yaml

        playbook_text = playbook_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(playbook_text)
    except Exception as e:
        return [{"type": "yaml_parse", "file": str(playbook_file), "stderr": str(e)}]

    container_port_usage = False
    pod_publish_defined = False

    def walk(node: Any) -> None:
        nonlocal container_port_usage, pod_publish_defined

        if isinstance(node, dict):
            if "containers.podman.podman_container" in node:
                container_config = node["containers.podman.podman_container"]
                if isinstance(container_config, dict):
                    if "ports" in container_config:
                        container_port_usage = True
                        errors.append({
                            "type": "podman_container_ports",
                            "file": str(playbook_file),
                            "stderr": "Do not define ports on podman_container when using a shared pod.",
                        })
                    if "environment" in container_config:
                        errors.append({
                            "type": "podman_environment_key",
                            "file": str(playbook_file),
                            "stderr": "Use env instead of environment for podman_container.",
                        })
            if "containers.podman.podman_pod" in node:
                pod_config = node["containers.podman.podman_pod"]
                if isinstance(pod_config, dict) and "publish" in pod_config:
                    pod_publish_defined = True
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parsed)

    if container_port_usage and not pod_publish_defined:
        errors.append({
            "type": "pod_publish_missing",
            "file": str(playbook_file),
            "stderr": "Define podman_pod.publish when exposing ports.",
        })

    return errors


def run_validation(safe_root: Path, inventory_file: Path, playbook_file: Path, php_file: Path) -> Tuple[List[dict], str, str]:
    validation_errors: List[dict] = []
    import yaml

    try:
        if not playbook_file.exists():
            validation_errors.append({"type": "missing_playbook", "file": str(playbook_file)})
        else:
            parsed = yaml.safe_load(playbook_file.read_text(encoding="utf-8"))
            if not isinstance(parsed, list):
                validation_errors.append({"type": "invalid_playbook", "file": str(playbook_file), "stderr": "Playbook must be a YAML list."})
    except Exception as e:
        validation_errors.append({"type": "yaml_parse", "file": str(playbook_file), "stderr": str(e)})

    validation_errors.extend(validate_podman_playbook(playbook_file))
    validation_errors.extend(validate_cross_file_consistency(playbook_file, php_file))

    stdout = ""
    stderr = ""

    if inventory_file.exists() and playbook_file.exists():
        remote_cmd = f"cd {REMOTE_PROJECT_ROOT} && ansible-playbook -i ansible/inventory.ini ansible/playbook.yml --check"
        code, stdout, stderr = run_remote_command(ANSIBLE_CONTROL_NODE, remote_cmd)
        if code != 0:
            validation_errors.append({"type": "ansible_syntax", "file": str(playbook_file), "stdout": stdout, "stderr": stderr})

    print("RETURN ERROR COUNT =", len(validation_errors))
    return validation_errors, stdout, stderr


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


def repair_validation_errors(
    validation_errors: List[dict],
    validation_stdout: str,
    validation_stderr: str,
    architecture: str,
    rules: str,
    format_rules: str,
    safe_root: Path,
    target_file_override: Optional[str] = None,
) -> None:
    for err in validation_errors:
        file_value = err.get("file")
        if target_file_override:
            target_file = target_file_override
        elif file_value:
            try:
                target_file = str(Path(file_value).resolve().relative_to(safe_root.resolve()))
            except ValueError:
                target_file = "ansible/playbook.yml"
        else:
            target_file = "ansible/playbook.yml"

        print(f"[ERROR] {target_file}")
        print("BEFORE REGENERATE")

        regeneration_context = {
            "source": "validation",
            "errors": validation_errors,
            "stdout": validation_stdout,
            "stderr": validation_stderr,
        }

        regenerated = regenerate_file_with_context(
            target_file,
            architecture,
            regeneration_context,
            rules,
            format_rules,
        )
        regenerated = extract_file_content_from_response(regenerated)
        print("AFTER REGENERATE")
        print("===== REGENERATED HEAD =====")
        print(regenerated)

        regenerated = repair_podman_yaml_content(regenerated)
        safe_write_file(safe_root, target_file, regenerated)
        print("AFTER WRITE")
        print("===== FILE AFTER WRITE =====")
        print((safe_root / target_file).read_text(encoding="utf-8")[:600])

        code, stdout, stderr = run_command([
            "scp",
            "-r",
            str(safe_root),
            f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
        ])

        print("AFTER SCP")
        print("SCP RETURN =", code)

        remote_target = target_file.replace("\\", "/")
        code2, stdout2, stderr2 = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            f"sed -n '1,30p' {REMOTE_PROJECT_ROOT}/{remote_target}"
        )

        print("===== REMOTE FILE =====")
        print(stdout2)

        if stdout:
            print(stdout)
        if stderr:
            print(stderr)

        code4, stdout4, stderr4 = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            "ls -l /home/vboxuser/containers/html"
        )

        print("===== HOST HTML DIR =====")
        print(stdout4)

        code3, stdout3, stderr3 = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            "podman exec php sh -c 'head -20 /var/www/html/index.php'"
        )

        print("===== CONTAINER FILE =====")
        print(stdout3)
        if stderr3:
            print(stderr3)


# =========================================================
# Deploy
# =========================================================

def deploy_pipeline() -> Dict[str, Any]:
    print()
    print("===== DEPLOY =====")

    remote_cmd = (
        f"cd {REMOTE_PROJECT_ROOT} && "
        "ansible-playbook "
        "-i ansible/inventory.ini "
        "ansible/playbook.yml"
    )

    code, stdout, stderr = run_remote_command(ANSIBLE_CONTROL_NODE, remote_cmd)
    stdout = stdout or ""
    stderr = stderr or ""

    print(stdout)
    if stderr:
        print(stderr)
    print("Return code =", code)

    return {"success": code == 0, "stdout": stdout, "stderr": stderr}


def run_browser_validation() -> Dict[str, Any]:
    """デプロイ後のブラウザ検証を実行する。"""

    url = "http://192.168.122.10:8080"
    code, stdout, stderr = run_command(["curl", "-sS", "-D", "-", url])
    stdout = stdout or ""
    stderr = stderr or ""

    headers_text = stdout
    body_text = ""
    for separator in ("\r\n\r\n", "\n\n"):
        if separator in stdout:
            headers_text, body_text = stdout.split(separator, 1)
            break

    header_lines = [line for line in headers_text.splitlines() if line]
    status_line = header_lines[0] if header_lines else ""
    status_code = 200
    if status_line.startswith("HTTP/"):
        status_code = int(status_line.split()[1])

    headers: Dict[str, str] = {}
    for line in header_lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()

    return {
        "success": code == 0,
        "status": status_code,
        "body": body_text,
        "headers": headers,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_php_lint() -> Dict[str, Any]:
    """対象 PHP ファイルの構文チェックを実行する。"""

    remote_cmds = [
        "php -l /var/www/html/index.php",
        "podman run --rm -v /home/vboxuser/containers/html:/var/www/html php:8.2-apache php -l /var/www/html/index.php",
    ]

    for remote_cmd in remote_cmds:
        code, stdout, stderr = run_remote_command(EXECUTION_NODE, remote_cmd)
        if code == 0:
            return {"success": True, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}
        if "command not found" not in (stderr or "").lower() and "not found" not in (stderr or "").lower():
            return {"success": False, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}

    return {"success": False, "exit_code": 127, "stdout": "", "stderr": "php command not found"}


# =========================================================
# main()
# =========================================================

def main() -> None:
    context = load_context()

    data, raw_output = generate_initial_data(context)

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

    print("Remote validation...")
    run_command([
        "scp",
        "-r",
        str(SAFE_ROOT),
        f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
    ])

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

    deploy_success = False
    if validation_success:
        print("\nValidation passed")
        print(playbook_file.read_text())
        deploy_result = deploy_pipeline()
        deploy_success = deploy_result["success"]

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
                )

                if not browser_issues and not lint_issues:
                    break

                repair_target = "src/index.php"
                repair_validation_errors(
                    [{"type": issue["type"], "file": str(playbook_file), "stderr": issue["detail"]} for issue in browser_issues + lint_issues],
                    browser_result.get("stdout", "") + "\n" + lint_result.get("stdout", ""),
                    browser_result.get("stderr", "") + "\n" + lint_result.get("stderr", ""),
                    context["architecture"],
                    context["rules"],
                    context["format_rules"],
                    SAFE_ROOT,
                    target_file_override=repair_target,
                )

                print("\n===== REDEPLOY AFTER REPAIR =====")
                deploy_result = deploy_pipeline()
                deploy_success = deploy_result["success"]
                if not deploy_success:
                    break

    if validation_success and deploy_success:
        print("\nPipeline completed successfully")
    elif not validation_success:
        raise RuntimeError("Validation retry exhausted")
    else:
        raise RuntimeError("Deploy failed")


if __name__ == "__main__":
    main()
