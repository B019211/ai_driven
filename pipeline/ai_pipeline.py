from pathlib import Path
from datetime import datetime
import base64
import binascii
import json
import os
import re
import time
import subprocess
import urllib.request
import urllib.error
import yaml

from difflib import get_close_matches
from typing import Any, Dict, List, Tuple, Optional, Set

from dotenv import load_dotenv
from json_repair import repair_json
from jsonschema import validate, ValidationError

from config import (
    BLOCKING_SEVERITIES,
    MAX_RETRY,
    MAX_REVIEW_SCHEMA_RETRY,
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
    normalize_generated_path,
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
    check_pod_state,
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
# Ollama Native API
# =========================================================

OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 1200


def ollama_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    num_predict: int = 2048,
    think: bool = False,
) -> str:
    """
    Call Ollama Native Chat API.

    Returns:
        The assistant message content as plain text.
    """

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
        "think": think,
    }

    request = urllib.request.Request(
        OLLAMA_API_URL,
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT,
        ) as response:
            response_data = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Ollama API HTTP error "
            f"{e.code}: {body}"
        ) from e

    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama API connection failed: {e}"
        ) from e

    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama API returned invalid JSON: {e}"
        ) from e

    message = response_data.get("message", {})
    content = message.get("content")

    if not isinstance(content, str) or not content:
        raise RuntimeError(
            "Ollama API returned empty message.content"
        )

    return content


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
      "required": ["category", "root_cause", "reason", "confidence"],
      "additionalProperties": False
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

    text = ollama_chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        num_predict=4098,
        think=False,
    )

    if not text:
        raise RuntimeError(
            "Ollama returned empty response."
        )

    return strip_markdown_fence(text).strip()


def regenerate_file_with_context(
    path: str,
    architecture: str,
    context_data: Dict[str, Any],
    rules: str,
    task_rules: str,
    format_rules: str,
) -> str:
    """
    AI-driven file repair.

    Repair AI returns the complete repaired content of the
    existing target file.

    Python does not apply old/new text patches.
    The returned file is validated before the caller writes it.
    """

    print("=== REPAIR V2 START ===")
    print(path)

    target = SAFE_ROOT / path
    repair_rules = (
        PROJECT_ROOT / "context/repair_rules.md"
    ).read_text(encoding="utf-8")

    repair_prompt = (
        PROJECT_ROOT / "prompts/repairer.txt"
    ).read_text(encoding="utf-8")

    if not target.exists():
        raise FileNotFoundError(
            f"Repair target does not exist: {target}"
        )

    current_file = target.read_text(encoding="utf-8")

    errors = context_data.get("errors", [])

    validation_evidence = context_data.get(
        "validation_evidence",
        {},
    )

    deploy_diagnosis = context_data.get(
        "deploy_diagnosis",
        {},
    )

    contract_feedback = context_data.get(
        "contract_feedback",
        "",
    )

    deployment_contract = context_data.get(
        "deployment_contract", {}, 
    )

    print("===== CONTRACT FEEDBACK =====")
    print(contract_feedback)
    print("=============================")

    print("===== DEPLOYMENT CONTRACT =====")
    print(json.dumps(
        deployment_contract,
        ensure_ascii=False, indent=2,
    ))
    print("===============================")


    # =========================================================
    # Repair AIへ渡す情報を最小化する
    # =========================================================
    errors_text = json.dumps(
        errors,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    contract_text = json.dumps(
        deployment_contract,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    if contract_feedback:
        # Infrastructure Contract Repair:
        # 決定論的Contract違反と現在ファイルを中心に修復する。
        prompt = f"""
    TARGET FILE:
    {path}

    CONTRACT VIOLATIONS:
    {contract_feedback}

    DEPLOYMENT CONTRACT:
    {contract_text}

    CURRENT FILE:
    --- BEGIN CURRENT FILE ---
    {current_file}
    --- END CURRENT FILE ---

    REPAIR RULES:
    {repair_rules}

    Repair ONLY the reported contract violations.
    Preserve all valid existing structure and content.
    Do not redesign the file.
    Do not add unrelated resources.
    Do not change values that are not required by the reported violations.

    Return exactly one JSON object.
    The JSON object must contain exactly one key: content.
    The value of content must be the complete repaired file content.
    Do not return YAML directly.
    Do not return Markdown.
    Do not use code fences.
    """

    else:
        # Runtime / deployment repair:
        # 実測結果と診断をRepair AIへ渡す。
        validation_evidence_text = json.dumps(
            validation_evidence,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        deploy_diagnosis_text = json.dumps(
            deploy_diagnosis,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        prompt = f"""
    TARGET FILE:
    {path}

    REPAIR EVIDENCE:
    {errors_text}

    RUNTIME VALIDATION EVIDENCE:
    {validation_evidence_text}

    DEPLOY DIAGNOSIS:
    {deploy_diagnosis_text}

    DEPLOYMENT CONTRACT:
    {contract_text}

    CURRENT FILE:
    {current_file}

    REPAIR RULES:
Repair only the reported runtime problem.

Preserve the existing file structure and every valid task.

Do not delete, rename, reorder, or redesign existing tasks unless the reported problem directly requires that exact change.

Do not replace valid Ansible module parameters with alternative parameter names.

Do not replace valid literal values with Jinja expressions, environment lookups, or variables.

Do not change hosts, task names, module names, images, volumes, env keys, command structure, or copy tasks unless the reported problem specifically requires that field to change.

The smallest possible edit is required.

Do not redesign the file.

Do not add unrelated resources.

Do not modify values that are not required to fix the reported runtime problem.

The Infrastructure Contract values are authoritative.

For PHP container environment variables, preserve the exact Deployment Contract values:
db_host = mysql
db_port = 3306
db_name = testdb
db_user = root
db_password = secret

Do not replace these values with Jinja expressions.

Do not use environment variable lookups for these PHP environment values.

Do not move these values to another container.

Repair ONLY the reported problem.

Return exactly one JSON object.

The JSON object must contain exactly one key: content.

The value of content must be the complete repaired file content.

Do not return YAML directly.

Do not return Markdown.

Do not use code fences.

Do not return explanations.

Do not return analysis.
    """

# repairのトークンチェック
    print("\n===== ACTUAL REPAIR PROMPT =====")
    print(prompt)
    print("================================")
#    raise RuntimeError("STOP: inspect actual repair prompt")

    print(f"Repair prompt length = {len(prompt):,} chars")
    print("Calling Ollama...")

    system_prompt = (
        PROJECT_ROOT / "prompts/repairer.txt"
    ).read_text(encoding="utf-8")

    raw = ollama_chat(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.0,
        num_predict=4096,
        think=False,
    )

    if not raw:
        raise RuntimeError(
            "Ollama returned empty content."
        )

    print("content =", repr(raw))
    print("RAW LENGTH =", len(raw))
    print("===== RAW TAIL =====")
    print(raw[-2000:])
    print("====================")

    print("===== REPAIR RAW =====")
    print(raw)
    print("======================")

    try:
        repair_result = safe_json_loads(
            sanitize_json_string(
                extract_json(raw)
            )
        )
    except Exception as e:
        raise RuntimeError(
            f"Repair response JSON parsing failed: {e}"
        ) from e

    if not isinstance(repair_result, dict):
        raise RuntimeError(
            "Repair response must be a JSON object."
        )

    repaired_file = repair_result.get("content")

    if not isinstance(repaired_file, str):
        files = repair_result.get("files")

        if isinstance(files, list) and len(files) == 1:
            file_data = files[0]

            if (
                isinstance(file_data, dict)
                and file_data.get("path") == path
                and isinstance(file_data.get("content"), str)
            ):
                repaired_file = file_data["content"]

    if not isinstance(repaired_file, str):
        raise RuntimeError(
            "Repair response must contain string 'content' "
            "or exactly one matching file in 'files'."
        )

    repaired_file = strip_markdown_fence(
    repaired_file
    ).strip()

    # =========================================================
    # Repair AI が現在ファイル用の区切り文字を
    # content 内に混入させる場合があるため除去する。
    # これはファイル内容ではなく、プロンプト上の
    # 表示用マーカーなので、YAML検証前に取り除く。
    # =========================================================

    begin_marker = "--- BEGIN CURRENT FILE ---"
    end_marker = "--- END CURRENT FILE ---"

    if repaired_file.startswith(begin_marker):
        repaired_file = repaired_file[
            len(begin_marker):
        ].lstrip()

    if repaired_file.endswith(end_marker):
        repaired_file = repaired_file[
            :-len(end_marker)
        ].rstrip()

    if not repaired_file:
        raise RuntimeError(
            "Repair produced empty file content."
        )

    if repaired_file == current_file:
        print("Repair produced no file change.")
        return current_file



    # =========================================================
    # Deterministic validation before writing
    # =========================================================

    if path.endswith((".yml", ".yaml")):
        try:
            repaired_file = postprocess_regenerated_file_content(
                repaired_file,
                path,
            )
            parsed_yaml = yaml.safe_load(repaired_file)
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"Repair produced invalid YAML: {e}"
            ) from e

        # Ansible playbook の root は必ず list。
        # LLM が単一 play を mapping として返した場合は
        # 決定論的に1 playへ正規化する。
        if (
            path == "ansible/playbook.yml"
            and isinstance(parsed_yaml, dict)
            and "hosts" in parsed_yaml
            and "tasks" in parsed_yaml
        ):
            parsed_yaml = [parsed_yaml]

            repaired_file = yaml.safe_dump(
                parsed_yaml,
                sort_keys=False,
                allow_unicode=True,
            )

            print(
                "\n=== ANSIBLE PLAYBOOK ROOT NORMALIZED ==="
            )
            print(repaired_file)

        if (
            path == "ansible/playbook.yml"
            and not isinstance(parsed_yaml, list)
        ):
            raise RuntimeError(
                "Repair produced invalid Ansible Playbook: "
                "playbook root must be a YAML list."
            )

        # Ansible playbook structure validation
        if path == "ansible/playbook.yml":

            for index, play in enumerate(parsed_yaml):

                if not isinstance(play, dict):
                    raise RuntimeError(
                        "Repair produced invalid Ansible Playbook: "
                        f"play at index {index} must be a mapping."
                    )

                if "hosts" not in play:
                    raise RuntimeError(
                        "Repair produced invalid Ansible Playbook: "
                        f"play at index {index} is missing 'hosts'."
                    )

                if "tasks" not in play:
                    raise RuntimeError(
                        "Repair produced invalid Ansible Playbook: "
                        f"play at index {index} is missing 'tasks'."
                    )

                if not isinstance(play["tasks"], list):
                    raise RuntimeError(
                        "Repair produced invalid Ansible Playbook: "
                        f"'tasks' at play index {index} must be a list."
                    )

            # Infrastructure contract validation
            contract_errors = validate_infrastructure_playbook_contract(
                parsed_yaml
            )

            if contract_errors:
                print(
                    "===== REPAIR CONTRACT VALIDATION FAILED ====="
                )

                for error in contract_errors:
                    print(f"- {error}")

                raise RuntimeError(
                    "Infrastructure contract violation:\n"
                    + "\n".join(contract_errors)
                )

    print("===== REPAIR V2 RESULT =====")
    print(repaired_file)
    print("=============================")

    return repaired_file


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

    content = ollama_chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        num_predict=4096,
        think=False,
    )

    if content is None:
        raise RuntimeError("Empty response from model")

    return strip_markdown_fence(content).strip()


# =========================================================
# Generate
# =========================================================

def load_context(
    task_type: str,
    previous_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    print(f"\n===== LOAD CONTEXT: {task_type} =====")

    architecture = (PROJECT_ROOT / "context/architecture.md").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "context/system_rules.md").read_text(encoding="utf-8")
    format_rules = (PROJECT_ROOT / "context/output_format.md").read_text(encoding="utf-8")
    review_rules = (PROJECT_ROOT / "context/reviewer_rules.md").read_text(encoding="utf-8")
    reviewer_prompt = (PROJECT_ROOT / "prompts/reviewer.txt").read_text(encoding="utf-8")

    if task_type == "infrastructure":
        task_rules = (PROJECT_ROOT / "context/infra_rules.md").read_text(encoding="utf-8")
        task_review_rules = (
            PROJECT_ROOT / "context/infra_reviewer_rules.md"
        ).read_text(encoding="utf-8")

    elif task_type == "application":
        task_rules = (PROJECT_ROOT / "context/app_rules.md").read_text(encoding="utf-8")
        task_review_rules = (
            PROJECT_ROOT / "context/app_reviewer_rules.md"
        ).read_text(encoding="utf-8")

    else:
        raise ValueError(f"Unsupported task type: {task_type}")

    deployment_contract = {
        "web_url": "http://192.168.122.10:8080",
        "db_host": "mysql",
        "db_port": 3306,
        "db_name": "testdb",
        "db_user": "root",
        "db_password": "secret",
    }

    if previous_context:
        deployment_contract.update(
            previous_context.get("deployment_contract", {})
        )

    print("Context loaded")

    return {
        "task_type": task_type,
        "architecture": architecture,
        "rules": rules,
        "format_rules": format_rules,
        "review_rules": review_rules,
        "task_rules": task_rules,
        "task_review_rules": task_review_rules,
        "reviewer_prompt": reviewer_prompt,
        "deployment_contract": deployment_contract,
    }

def load_task(task_name: str) -> str:
    path = TASK_DIR / task_name

    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    return path.read_text(encoding="utf-8")

def generate_initial_data(
    context: Dict[str, Any],
    task_name: str,
    task: str,
) -> Tuple[Dict[str, Any], str]:
    print("\n===== GENERATE PROMPT =====")

    task_type = Path(task_name).stem
    print(f"Task Type = {task_type}")

    if task_type == "infrastructure":
        system_prompt_path = (
            PROJECT_ROOT / "context/infra_generation_rules.md"
        )

        generation_target = """
    Generate only this file:

    ansible/playbook.yml
    """

    elif task_type == "application":
        system_prompt_path = (
            PROJECT_ROOT / "prompts/php_engineer.txt"
        )

        generation_target = """
    Generate the required application files defined by the Task.
    """

    else:
        raise ValueError(
            f"Unsupported generation task type: {task_type}"
        )

    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    prompt = f"""
        Task:
        {task}

        Generation target:
        {generation_target}

        Task Rules:
        {context['task_rules']}

        Generation Rules:
        {context['rules']}

        Deployment Contract:
        {json.dumps(context.get("deployment_contract", {}), indent=2)}

        Output Format:
        {context['format_rules']}
    """

    print("Deployment Contract:")
    print(json.dumps(
        context.get("deployment_contract", {}),
        indent=2,
        ensure_ascii=False
    ))


    print(f"Prompt length = {len(prompt):,} chars")

    print("\n===== GENERATE START =====")
    start = time.time()

    print("Calling Ollama...")
    ollama_start = time.monotonic()

    print("SYSTEM PROMPT LENGTH =", len(system_prompt))
    print("USER PROMPT LENGTH =", len(prompt))
    print("MODEL =", MODEL_NAME)

    try:
        raw_output = ollama_chat(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.0,
            num_predict=2048,
            think=False,
        )

        ollama_elapsed = time.monotonic() - ollama_start
        print(
            f"Ollama returned ({ollama_elapsed:.1f}s)"
        )

    except Exception as e:
        ollama_elapsed = time.monotonic() - ollama_start

        print(
            f"Ollama call failed after "
            f"{ollama_elapsed:.1f}s"
        )

        raise RuntimeError(
            f"Failed to call Ollama: {e}"
        )

    elapsed = time.time() - start
    print(f"Generate finished ({elapsed:.1f}s)")

    if not raw_output:
        raise RuntimeError(
            "Ollama returned empty content."
        )

    print("content =", repr(raw_output))
    print("RAW LENGTH =", len(raw_output))
    print("===== RAW TAIL =====")
    print(raw_output[-2000:])
    print("====================")

    json_text = extract_json(raw_output)

    try:
        data = json.loads(json_text)

    except json.JSONDecodeError:
        print(
            "Initial JSON parse failed. "
            "Attempting JSON repair."
        )

        json_text = sanitize_json_string(json_text)
        data = safe_json_loads(json_text)

    # Infrastructure fixed artifacts are assembled by Python.
    # They are defined explicitly by infra_rules.md and do not
    # require LLM generation.
    if task_type == "infrastructure":

        generated_files = data.get("files", [])

        playbook_files = [
            f
            for f in generated_files
            if f.get("path") == "ansible/playbook.yml"
        ]

        if len(playbook_files) != 1:
            raise RuntimeError(
                "Infrastructure Generate must return exactly "
                "one ansible/playbook.yml file."
            )

        data["files"] = [
            playbook_files[0],
            {
                "path": "ansible/inventory.ini",
                "content": "[control]\nasbsvr\n\n[execution]\nrockey8\n",
            },
            {
                "path": "src/index.php",
                "content": "<?php\necho \"Infrastructure OK\";\n?>\n",
            },
        ]

        # ---------------------------------------------------------
        # Repair V2 用の初期成果物を SAFE_ROOT に保存する。
        # Contract validation より前に作業対象ファイルを確保する。
        # ---------------------------------------------------------
        for file_entry in data["files"]:
            relative_path = normalize_generated_path(
                file_entry["path"]
            )
            content = file_entry.get("content", "")

            safe_write_file(
                SAFE_ROOT,
                relative_path,
                content,
            )


        # ---------------------------------------------------------
        # Infrastructure Contract validation / repair
        # Generate直後に決定論的に検査する。
        # ---------------------------------------------------------

        playbook_content = playbook_files[0]["content"]

        try:
            parsed_playbook = yaml.safe_load(
                playbook_content
            )

        except yaml.YAMLError as e:
            yaml_error = str(e)

            repaired_files = repair_validation_errors(
                [
                    {
                        "type": "infrastructure_yaml",
                        "file": "ansible/playbook.yml",
                        "detail": yaml_error,
                    }
                ],
                yaml_error,
                "",
                context["architecture"],
                context["rules"],
                context["task_rules"],
                context["format_rules"],
                SAFE_ROOT,
                target_file_override="ansible/playbook.yml",
                contract_feedback=(
                    "Infrastructure YAML parse failed:\n"
                    + yaml_error
                ),
                deployment_contract=context.get("deployment_contract", {}),
            )

            for file_entry in data["files"]:
                repaired_content = repaired_files.get(
                    file_entry["path"]
                )

                if repaired_content is not None:
                    file_entry["content"] = repaired_content

            # Repair後のPlaybookを再取得して、
            # 必ずYAMLとして再検証する
            playbook_content = playbook_files[0]["content"]

            try:
                parsed_playbook = yaml.safe_load(
                    playbook_content
                )

            except yaml.YAMLError as repair_error:
                raise RuntimeError(
                    "Infrastructure Repair produced invalid YAML: "
                    f"{repair_error}"
                ) from repair_error

        contract_errors = (
            validate_infrastructure_playbook_contract(
                parsed_playbook
            )
        )

        if contract_errors:
            repaired_files = repair_validation_errors(
                [
                    {
                        "type": "infrastructure_contract",
                        "file": "ansible/playbook.yml",
                        "detail": error,
                    }
                    for error in contract_errors
                ],
                "",
                "",
                context["architecture"],
                context["rules"],
                context["task_rules"],
                context["format_rules"],
                SAFE_ROOT,
                target_file_override="ansible/playbook.yml",
                contract_feedback="\n".join(
                    contract_errors
                ),
                deployment_contract=context.get("deployment_contract", {}),
            )

            for file_entry in data["files"]:
                repaired_content = repaired_files.get(
                    file_entry["path"]
                )

                if repaired_content is not None:
                    file_entry["content"] = repaired_content

    # ---------------------------------------------------------
    # Final generated JSON schema validation
    # ---------------------------------------------------------

    generation_fixer_prompt = (
        PROJECT_ROOT / "prompts/generation_fixer.txt"
    ).read_text(encoding="utf-8")

    try:
        validate(
            instance=data,
            schema=OUTPUT_SCHEMA,
        )

    except ValidationError as e:
        print("\nSchema validation failed")
        print(e)

        repair_prompt = f"""
Validation error:
{str(e)}

Current generated JSON:
{json.dumps(data, ensure_ascii=False, indent=2)}

Output Format:
{context['format_rules']}
"""

        repair_raw = ollama_chat(
            messages=[
                {
                    "role": "system",
                    "content": generation_fixer_prompt,
                },
                {
                    "role": "user",
                    "content": repair_prompt,
                },
            ],
            temperature=0.0,
            num_predict=2048,
            think=False,
        )

        if not repair_raw:
            raise RuntimeError(
                "Schema repair returned empty response."
            )

        repair_json = extract_json(repair_raw)
        repair_json = sanitize_json_string(
            repair_json
        )

        data = safe_json_loads(repair_json)

        validate(
            instance=data,
            schema=OUTPUT_SCHEMA,
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            "Generated result must be object"
        )

    return data, raw_output


# =========================================================
# Review
# =========================================================
                
def review_loop(data: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    retry_count = 0
    schema_retry_count = 0

    while True:
        print("\n===== REVIEW =====")
        print(f"Attempt {retry_count + 1}")

        print("\n===== REVIEW INPUT PLAYBOOK =====")
        for file_entry in data.get("files", []):
            if file_entry.get("path") == "ansible/playbook.yml":
                print(file_entry.get("content", ""))

        artifact_facts = ""

        if context.get("task_type") == "infrastructure":
            playbook_entry = next(
                (
                    f
                    for f in data.get("files", [])
                    if f.get("path") == "ansible/playbook.yml"
                ),
                None,
            )

            if playbook_entry:
                try:
                    parsed_playbook = yaml.safe_load(
                        playbook_entry.get("content", "")
                    )

                    facts = ["YAML parse: success",]

                    if isinstance(parsed_playbook, list):
                        facts.append(
                            f"Play count: {len(parsed_playbook)}"
                        )

                        for index, play in enumerate(parsed_playbook):
                            if not isinstance(play, dict):
                                facts.append(
                                    f"Play {index}: invalid play structure"
                                )
                                continue

                            facts.append(
                                f"Play {index} hosts: {play.get('hosts')!r}"
                            )

                            tasks = play.get("tasks")

                            if isinstance(tasks, list):
                                facts.append(
                                    f"Play {index} tasks count: {len(tasks)}"
                                )
                                facts.append(
                                    "Play {} task names: {!r}".format(
                                        index,
                                        [
                                            task.get("name")
                                            for task in tasks
                                            if isinstance(task, dict)
                                        ],
                                    )
                                )
                            else:
                                facts.append(
                                    f"Play {index} tasks: {tasks!r}"
                                )

                    artifact_facts = "\n".join(facts)

                except yaml.YAMLError as e:
                    artifact_facts = f"YAML parse error: {e}"

        review_request = f"""
        Generated JSON:

        {json.dumps(data, ensure_ascii=False)}

        Artifact Facts:
        {artifact_facts}

        Project Rules:
        {context['rules']}

        Task Rules:
        {context['task_rules']}

        Review Rules:
        {context['review_rules']}

        Task Review Rules:
        {context['task_review_rules']}

        Review the generated artifact according to the supplied rules.
        Return JSON only.
        """

        print(f"\n=== REVIEW ATTEMPT {retry_count + 1} ===")
        print("Review request...")
        start = time.time()
        print("REVIEW SYSTEM PROMPT LENGTH =", len(context["reviewer_prompt"]))
        print("REVIEW USER PROMPT LENGTH =", len(review_request))
        print("===== REVIEW SYSTEM PROMPT TAIL =====")
        print(context["reviewer_prompt"][-3000:])
        print("=====================================")


        review_raw = ollama_chat(
            messages=[
                {
                    "role": "system",
                    "content": context["reviewer_prompt"],
                },
                {
                    "role": "user",
                    "content": review_request,
                },
            ],
            temperature=0.0,
            num_predict=2048,
            think=False,
        )

        print(f"Review finished ({time.time() - start:.1f}s)")
        print("\n=== REVIEW RAW ===")
        print(review_raw)

        print("\n===== REVIEW REQUEST FULL DEBUG =====")
        print(review_request)
        print("====================================")

        if "remove_all_files" in review_request:
            print("!!! remove_all_files FOUND IN REVIEW REQUEST !!!")
        else:
            print("remove_all_files NOT FOUND IN REVIEW REQUEST")

        review_json = extract_json(review_raw)
        review_json = sanitize_json_string(review_json)
        review_data = safe_json_loads(review_json)

        # try:
            # # =====================================================
            # # Optional fields fallback
            # # =====================================================
            # review_data.setdefault(
            #     "approved",
            #     False,
            # )

            # review_data.setdefault(
            #     "summary",
            #     "Reviewer rejected or approved the generated artifact."
            # )

            # review_data.setdefault(
            #     "risks",
            #     [],
            # )

            # # =====================================================
            # # Diagnosis normalization
            # # =====================================================
            # # Reviewer may explicitly return diagnosis=null when
            # # there is no blocking problem. Normalize it before
            # # schema validation because REVIEW_SCHEMA requires
            # # diagnosis to be an object.
            # if review_data.get("diagnosis") is None:
            #     review_data["diagnosis"] = {
            #         "category": context.get("task_type", "application"),
            #         "root_cause": "",
            #         "reason": "",
            #         "confidence": 0.0,
            #     }

        try:
            validate(
                instance=review_data,
                schema=REVIEW_SCHEMA,
            )

        except ValidationError as e:
            schema_retry_count += 1

            print("\n===== REVIEW SCHEMA INVALID =====")
            print(
                f"Schema retry = "
                f"{schema_retry_count}/{MAX_REVIEW_SCHEMA_RETRY}"
            )
            print(e)

            if schema_retry_count >= MAX_REVIEW_SCHEMA_RETRY:
                raise RuntimeError(
                    "Reviewer output schema invalid after maximum retries:\n"
                    f"{e}"
                ) from e

            schema_retry_prompt = f"""
        The previous Reviewer response violated REVIEW_SCHEMA.

        Validation error:
        {str(e)}

        Previous Reviewer response:
        {json.dumps(review_data, ensure_ascii=False, indent=2)}

        Review request:
        {review_request}

        Your previous response was invalid because it did not satisfy
        the required Reviewer output schema.

        Return a new Review JSON object that satisfies REVIEW_SCHEMA.

        Do not change the generated artifact.
        Do not perform artifact repair.
        Do not return explanations.
        Return JSON only.
        """

            print("\n===== REVIEW SCHEMA RETRY =====")
            print("Retrying Reviewer because its output schema was invalid.")

            retry_start = time.time()

            review_raw = ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": context["reviewer_prompt"],
                    },
                    {
                        "role": "user",
                        "content": schema_retry_prompt,
                    },
                ],
                temperature=0.0,
                num_predict=2048,
                think=False,
            )

            print(
                f"Review schema retry finished "
                f"({time.time() - retry_start:.1f}s)"
            )

            if not review_raw:
                raise RuntimeError(
                    "Reviewer schema retry returned empty response."
                )

            print("\n=== REVIEW SCHEMA RETRY RAW ===")
            print(review_raw)

            review_json = extract_json(review_raw)
            review_json = sanitize_json_string(review_json)
            review_data = safe_json_loads(review_json)

            try:
                validate(
                    instance=review_data,
                    schema=REVIEW_SCHEMA,
                )
            except ValidationError as retry_error:
                raise RuntimeError(
                    "Reviewer output schema invalid after schema retry:\n"
                    f"{retry_error}"
                ) from retry_error

            schema_retry_prompt = f"""
        The previous Reviewer response violated REVIEW_SCHEMA.

        Validation error:
        {str(e)}

        Previous Reviewer response:
        {json.dumps(review_data, ensure_ascii=False, indent=2)}

        Review request:
        {review_request}

        Your previous response was invalid because it did not satisfy
        the required Reviewer output schema.

        Return a new Review JSON object that satisfies REVIEW_SCHEMA.

        Do not change the generated artifact.
        Do not perform artifact repair.
        Do not return explanations.
        Return JSON only.
        """

            print("\n===== REVIEW SCHEMA RETRY =====")
            print("Retrying Reviewer because its output schema was invalid.")

            retry_start = time.time()

            review_raw = ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": context["reviewer_prompt"],
                    },
                    {
                        "role": "user",
                        "content": schema_retry_prompt,
                    },
                ],
                temperature=0.0,
                num_predict=2048,
                think=False,
            )

            print(
                f"Review schema retry finished "
                f"({time.time() - retry_start:.1f}s)"
            )

            if not review_raw:
                raise RuntimeError(
                    "Reviewer schema retry returned empty response."
                )

            print("\n=== REVIEW SCHEMA RETRY RAW ===")
            print(review_raw)

            review_json = extract_json(review_raw)
            review_json = sanitize_json_string(review_json)
            review_data = safe_json_loads(review_json)

            try:
                validate(
                    instance=review_data,
                    schema=REVIEW_SCHEMA,
                )
            except ValidationError as retry_error:
                raise RuntimeError(
                    "Reviewer output schema invalid after schema retry:\n"
                    f"{retry_error}"
                ) from retry_error

        # except ValidationError as e:
        #     raise RuntimeError(f"Review schema invalid:\n{e}")

        approved = review_data.get("approved", False)
        risks = review_data.get("risks", [])


        blocking = []
        warnings = []

        for r in risks:
            if not isinstance(r, dict):
                warnings.append({
                    "severity": "WARNING",
                    "description": r,
                })
                continue

            severity = r.get("severity")

            if severity in BLOCKING_SEVERITIES:
                blocking.append(r)
            else:
                warnings.append(r)

        # Reviewerが明示的にapproved=falseなら必ず失敗扱い
        if not approved:
            if not blocking:
                blocking.append({
                    "severity": "BLOCKING",
                    "description": (
                        review_data.get(
                            "summary",
                            "Reviewer rejected the generated artifact."
                        )
                    ),
                })

        if not blocking:
            print("\nReview passed")

            if warnings:
                print(f"Review warnings: {len(warnings)}")

            break

        # BLOCKING riskが1件でも存在する場合、
        # Reviewerのapproved=trueを信用して通過させない。
        print("\nBlocking risks found")

        retry_count += 1

        if retry_count >= MAX_RETRY:
            print("\nMax retry reached")

            if context.get("task_type") == "infrastructure":
                raise RuntimeError(
                    "Infrastructure review failed after maximum retries."
                )

            print("Continue pipeline with warnings")
            break

        print("\nBlocking risks found")

        fix_prompt = f"""
CURRENT GENERATED JSON:
{json.dumps(data, ensure_ascii=False, indent=2)}

BLOCKING REVIEW RISKS:
{json.dumps(blocking, ensure_ascii=False, indent=2)}

PROJECT RULES:
{context["rules"]}

TASK RULES:
{context["task_rules"]}

FORMAT RULES:
{context["format_rules"]}

REVIEW RULES:
{context["review_rules"]}

TASK REVIEW RULES:
{context["task_review_rules"]}

Repair the current generated JSON only for the supplied blocking review risks.

Preserve all valid existing content.
Do not change unrelated valid content.
Do not add unrequested files.
Do not remove required files.

Return the complete corrected JSON object.
Return JSON only.
"""

        retry_temp = max(0.05, 0.3 - (retry_count * 0.1))

        fix_raw = ollama_chat(
            messages=[
                {
                    "role": "system",
                    "content": Path(
                        "prompts/reviewer_fixer.txt"
                    ).read_text(encoding="utf-8"),
                },
                {
                    "role": "user",
                    "content": fix_prompt,
                },
            ],
            temperature=retry_temp,
            num_predict=2048,
            think=False,
        )
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

            fixed_files = {
                "ansible/inventory.ini": (
                    "[control]\n"
                    "asbsvr\n"
                    "\n"
                    "[execution]\n"
                    "rockey8\n"
                ),
                "src/index.php": (
                    "<?php\n"
                    'echo "Infrastructure OK";\n'
                    "?>\n"
                ),
            }

            for path in missing:
                if path in fixed_files:
                    data["files"].append({
                        "path": path,
                        "content": fixed_files[path],
                    })
                else:
                    content = regenerate_file(path)
                    data["files"].append({
                        "path": path,
                        "content": content,
                    })


    return data, review_data


# =========================================================
# Generate Files
# =========================================================

def generate_files(data: Dict[str, Any], allowed_paths: Optional[Set[str]] = None) -> Tuple[List[dict], Path, Path, Path]:
    validation_errors: List[dict] = []

    if allowed_paths is None:
        allowed_paths = ALLOWED_PATHS

    import shutil

    if not SAFE_ROOT.exists():
        SAFE_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"SAFE_ROOT = {SAFE_ROOT}")

    for file in data.get("files", []):
        relative_path = file.get("path", "")

        try:
            import yaml

            if relative_path.startswith("generated/files/"):
                relative_path = relative_path[len("generated/files/"):]
            print(f"\n===== FILE ===== {relative_path}")

            if relative_path:
                relative_path = normalize_generated_path(relative_path)

            content = file.get("content")

            if not relative_path:
                print("Skip invalid path")
                continue

            if not content:
                print(f"Skip empty content: {relative_path}")
                continue

            # Repair V2へ渡すため、Generate直後の元ファイルを保持する。
            # YAML Auto Fixが失敗しても、この内容を失わない。
            original_content = content

            if relative_path.endswith((".yml", ".yaml")):
                print("===== YAML INPUT =====")
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
                                content = ollama_chat(
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": Path(
                                                "prompts/yaml_repair.txt"
                                            ).read_text(encoding="utf-8"),
                                        },
                                        {
                                            "role": "user",
                                            "content": yaml_fix_prompt,
                                        },
                                    ],
                                    temperature=0.0,
                                    num_predict=4096,
                                    think=False,
                                )
                            except Exception as e:
                                if "503" in str(e):
                                    print(f"[WARN] Ollama unavailable "
                                          f"retry={attempt + 1}/3")
                                    time.sleep(10)
                                    continue
                                raise

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
            print("===== BEFORE WRITE =====")
            print(repr(content))

            safe_write_file(SAFE_ROOT, relative_path, content)

            written_path = SAFE_ROOT / relative_path

            print("===== AFTER WRITE =====")
            print(repr(written_path.read_text(encoding="utf-8")))

        except Exception as e:
            print(f"Failed processing {relative_path}")
            print(e)

            validation_errors.append({
                "type": "yaml_autofix_failed",
                "file": str(SAFE_ROOT / relative_path),
                "stderr": str(e),
            })

            # -------------------------------------------------
            # Repair V2 のために、元のファイル内容を保持する。
            #
            # YAML が不正でも「ファイルそのもの」を消してはいけない。
            # Repair V2 は現在ファイルを読み、
            # 最小限の old -> new 変更を生成する設計だからである。
            # -------------------------------------------------

            try:
                if relative_path and original_content:
                    safe_write_file(
                        SAFE_ROOT,
                        relative_path,
                        original_content,
                    )
                    print(
                        f"Preserved original invalid file for repair: "
                        f"{relative_path}"
                    )
            except Exception as write_error:
                print(
                    f"Failed to preserve invalid file "
                    f"{relative_path}: {write_error}"
                )

            continue

    inventory_file = SAFE_ROOT / "ansible/inventory.ini"
    playbook_file = SAFE_ROOT / "ansible/playbook.yml"
    php_file = SAFE_ROOT / "src/index.php"

    print("\n===== SAVED ARTIFACT CHECK =====")

    for path in [
        SAFE_ROOT / "ansible/playbook.yml",
        SAFE_ROOT / "ansible/inventory.ini",
        SAFE_ROOT / "src/index.php",
    ]:
        print(f"\n--- {path.relative_to(SAFE_ROOT)} ---")

        if path.exists():
            print(path.read_text(encoding="utf-8"))
        else:
            print("MISSING")


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


def validate_infrastructure_playbook_contract(
    parsed_yaml: Any,
) -> List[str]:
    """
    Validate mandatory runtime wiring for ansible/playbook.yml.

    These checks protect infrastructure invariants from accidental
    removal by the Repair Agent.
    """

    violations: List[str] = []

    required_host_html = "/home/vboxuser/containers/html"
    required_document_root = "/var/www/html"
    required_index_dest = (
        "/home/vboxuser/containers/html/index.php"
    )

    pod_found = False
    php_container_found = False
    php_volume_found = False
    index_copy_found = False

    required_php_env = {
        "db_host": "mysql",
        "db_port": 3306,
        "db_name": "testdb",
        "db_user": "root",
        "db_password": "secret",
    }

    if not isinstance(parsed_yaml, list):
        raise RuntimeError(
            "Infrastructure contract violation: "
            "playbook root must be a list."
        )

    for play in parsed_yaml:
        if not isinstance(play, dict):
            continue

        tasks = play.get("tasks", [])

        for task in tasks:
            if not isinstance(task, dict):
                continue

            # -----------------------------------------------------
            # LAMP pod must use the required podman_pod module shape
            # -----------------------------------------------------
            pod_cfg = task.get(
                "containers.podman.podman_pod"
            )

            if isinstance(pod_cfg, dict):
                if pod_cfg.get("name") == "lamp-pod":
                    pod_found = True

                if "name" not in pod_cfg:
                    violations.append(
                        "Infrastructure contract violation: "
                        "containers.podman.podman_pod must define "
                        "name: lamp-pod."
                    )

                if "pod_name" in pod_cfg or "container" in pod_cfg:
                    violations.append(
                        "Infrastructure contract violation: "
                        "containers.podman.podman_pod must use "
                        "name: lamp-pod and must not use "
                        "pod_name or container."
                    )

                if "publish_port_map" in pod_cfg:
                    violations.append(
                        "Infrastructure contract violation: "
                        "containers.podman.podman_pod must use "
                        "publish: 8080:80 "
                        "and must not use publish_port_map."
                    )


            # -----------------------------------------------------
            # PHP container must keep the host -> container bind mount
            # -----------------------------------------------------
            container_cfg = task.get(
                "containers.podman.podman_container"
            )

            if (
                isinstance(container_cfg, dict)
                and container_cfg.get("name") == "php"
            ):
                php_container_found = True

                # -------------------------------------------------
                # PHP container must receive the Deployment Contract
                # DB connection values through env:
                # -------------------------------------------------

                php_env = container_cfg.get("env")

                if not isinstance(php_env, dict):
                    violations.append(
                    "Infrastructure contract violation: "
                    "PHP container must define env: "
                    "for the required DB connection values."
                )
                else:
                    for key, expected_value in required_php_env.items():
                        if php_env.get(key) != expected_value:
                            violations.append(
                                "Infrastructure contract violation: "
                                f"PHP container env '{key}' must be "
                                f"'{expected_value}'."
                            )


                # -------------------------------------------------
                # PHP container must provide PDO MySQL support
                # -------------------------------------------------
                command = container_cfg.get("command")

                required_command = [
                    "sh",
                    "-c",
                    "docker-php-ext-install pdo_mysql && apache2-foreground",
                ]

                if command != required_command:
                    violations.append(
                        "Infrastructure contract violation: "
                        "PHP container must provide pdo_mysql using "
                        "the required Learning Phase startup command."
                    )

                volumes = container_cfg.get("volumes", [])

                if not isinstance(volumes, list):
                    raise RuntimeError(
                        "Infrastructure contract violation: "
                        "php container 'volumes' must be a list."
                    )

                for volume in volumes:
                    if not isinstance(volume, str):
                        continue

                    parts = volume.split(":")

                    if len(parts) >= 2:
                        host_path = parts[0]
                        container_path = parts[1]

                        if (
                            host_path == required_host_html
                            and container_path == required_document_root
                        ):
                            php_volume_found = True
                            break


            # -----------------------------------------------------
            # index.php must be copied to the host HTML directory
            # -----------------------------------------------------
            copy_cfg = task.get("ansible.builtin.copy")
            if copy_cfg is None:
                copy_cfg = task.get("copy")

            if isinstance(copy_cfg, dict):
                src = str(copy_cfg.get("src", ""))
                dest = str(copy_cfg.get("dest", ""))

                if (
                    src.endswith("src/index.php")
                    and dest == required_index_dest
                ):
                    index_copy_found = True

                    # Rocky Linux is RedHat family, not "Linux".
                    # The required copy task must not be skipped
                    # by this invalid condition.
                    when = task.get("when")

                    if (
                        isinstance(when, str)
                        and "ansible_os_family" in when
                        and "Linux" in when
                    ):
                        raise RuntimeError(
                            "Infrastructure contract violation: "
                            "index.php copy task must not use "
                            "ansible_os_family == 'Linux'."
                        )

    if not pod_found:
        violations.append(
            "Infrastructure contract violation: "
            "LAMP pod 'lamp-pod' was not found."
        )

    if not php_container_found:
        violations.append(
            "Infrastructure contract violation: "
            "PHP container was not found."
        )

    if not php_volume_found:
        violations.append(
            "Infrastructure contract violation: "
            "PHP container must bind "
            "/home/vboxuser/containers/html "
            "to /var/www/html."
        )

    if not index_copy_found:
        violations.append(
            "Infrastructure contract violation: "
            "index.php must be copied to "
            "/home/vboxuser/containers/html/index.php."
        )

    return violations

def postprocess_regenerated_file_content(
content: str,
target_file: str,
) -> str:
    """Apply extension-specific deterministic repair to regenerated content."""

    if not target_file.endswith((".yml", ".yaml")):
        return content

    repaired = repair_podman_yaml_content(content)

    # YAML document separators are not part of the generated file
    # contract for this project. Remove accidental leading/trailing
    # separators deterministically before YAML validation.
    lines = repaired.splitlines()

    while lines and lines[0].strip() == "---":
        lines.pop(0)

    while lines and lines[-1].strip() == "---":
        lines.pop()

    repaired = "\n".join(lines).strip() + "\n"

    if target_file == "ansible/playbook.yml":
        repaired = repaired.replace(
            "src:/home/vboxuser/containers/html:/var/www/html",
            "/home/vboxuser/containers/html:/var/www/html",
        )

    return repaired

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
    body_text = body.lower() if isinstance(body, str) else ""

    if isinstance(body, str) and "could not find driver" in body_text:
        issues.append({
            "type": "missing_pdo_driver",
            "category": "infrastructure",
            "severity": "blocker",
            "detail": "PHP PDO MySQL driver is missing. Install pdo_mysql in PHP container via ansible/playbook.yml.",
            "repair_target": "ansible/playbook.yml",
        })

    elif payload.get("success") is False and not (
        isinstance(status, int) and status >= 400
    ):
        issues.append({
            "type": "browser_connection_error",
            "category": "infrastructure",
            "severity": "blocker",
            "detail": payload.get("stderr", "Browser validation failed"),
            "repair_target": "ansible/playbook.yml",
        })

    if isinstance(status, int) and status >= 400:
        issues.append({
            "type": "browser_status",
            "category": "application" if status == 404 else "infrastructure",
            "severity": "warning",
            "detail": f"HTTP status {status}",
            "repair_target": "src/index.php" if status == 404 else "ansible/playbook.yml",
        })

    if isinstance(body, str) and ("fatal error" in body_text or "parse error" in body_text or "uncaught" in body_text):
        issues.append({
            "type": "browser_body",
            "category": "application",
            "severity": "warning",
            "detail": "Response body contains a PHP runtime or fatal error",
            "repair_target": "src/index.php",
        })

    content_type = headers.get("Content-Type") if isinstance(headers, dict) else None
    if isinstance(content_type, str) and "text/html" in content_type.lower() and not body.strip():
        issues.append({
            "type": "browser_empty",
            "category": "application",
            "severity": "warning",
            "detail": "HTML response body is empty",
            "repair_target": "src/index.php",
        })

    return issues


def analyze_php_lint_result(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """PHP Lint の結果を解析して問題を返す。"""

    issues: List[Dict[str, Any]] = []
    exit_code = payload.get("exit_code")
    stdout = payload.get("stdout") or ""
    stderr = payload.get("stderr") or ""
    combined = f"{stdout}\n{stderr}".strip()
    combined_lower = combined.lower()

    if exit_code == 0:
        return issues

    if combined:
        combined_lower = combined.lower()

    if (
        "could not open input file" in combined_lower
        or "no container with name or id" in combined_lower
        or "no such container" in combined_lower
    ):
        issues.append({
            "type": "php_lint_infrastructure",
            "category": "infrastructure",
            "severity": "blocker",
            "detail": combined,
            "repair_target": "ansible/playbook.yml",
        })
    else:
        issues.append({
            "type": "php_lint",
            "category": "application",
            "severity": "warning",
            "detail": combined or "PHP lint failed",
            "repair_target": "src/index.php",
        })

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
    task_rules: str,
    format_rules: str,
    safe_root: Path,
    target_file_override: Optional[str] = None,
    available_php_files: Optional[List[str]] = None,
    deploy_evidence: Optional[dict] = None,
    deploy_diagnosis=None,
    contract_feedback: str = "",
    deployment_contract: Optional[dict] = None,
) -> Dict[str, str]:

    # 同一ファイルは1回だけ修正
    target_files = set()
    repaired_files: Dict[str, str] = {}

    for err in validation_errors:
        file_value = err.get("file")

        if target_file_override:
            override_path = Path(target_file_override)

            if override_path.is_absolute():
                try:
                    target_file = str(
                        override_path.relative_to(safe_root.resolve())
                    ).replace("\\", "/")
                except ValueError:
                    target_file = str(override_path)
            else:
                target_file = target_file_override.replace("\\", "/")

            target_files.add(normalize_generated_path(target_file))

        elif file_value:
            resolved_file = Path(file_value)

            if not resolved_file.is_absolute():
                resolved_file = (safe_root / file_value).resolve()

            try:
                target_file = str(
                    resolved_file.relative_to(safe_root.resolve())
                ).replace("\\", "/")

                target_files.add(normalize_generated_path(target_file))

            except ValueError:
                raise RuntimeError(
                    f"Repair target is outside SAFE_ROOT: {file_value}"
                )

    for target_file in target_files:
        print(f"[ERROR] {target_file}")

        target_path = safe_root / target_file

        if not target_path.exists():
            raise RuntimeError(
                f"Repair target does not exist: {target_file}"
            )

        current_content = target_path.read_text(encoding="utf-8")

        # ============================================================
        # Deterministic Contract Repair
        # ============================================================
        #
        # 既知の Infrastructure Contract 違反は LLM に修正させない。
        # 今回は podman_pod の旧/誤キーだけを機械的に修正する。
        #
        # container/pod_name:
        #     → name:
        #
        # それ以外の内容は一切変更しない。
        # ============================================================

        deterministic_content = current_content

        if target_file == "ansible/playbook.yml":
            deterministic_content = deterministic_content.replace(
                "container/pod_name: lamp-pod",
                "name: lamp-pod",
            )

        if deterministic_content != current_content:
            print("===== DETERMINISTIC CONTRACT REPAIR =====")
            print(f"Target: {target_file}")
            print("Replace: container/pod_name: lamp-pod")
            print("With:    name: lamp-pod")

            safe_write_file(
                safe_root,
                target_file,
                deterministic_content,
            )

            repaired_files[target_file] = deterministic_content

            print("===== FILE AFTER DETERMINISTIC REPAIR =====")
            print(
                deterministic_content[:600]
            )

            print("Deterministic repair completed.")

            # 今回は既知の Contract 違反を修正できたので、
            # LLM Repair は実行しない。
            continue

        # ============================================================
        # AI Repair fallback
        # ============================================================

        print("BEFORE REGENERATE")

        # Runtime validation issues are the primary repair evidence.
        # Preserve all issues, but explicitly prioritize browser/runtime
        # failures so the Repair Agent does not overlook them.
        prioritized_errors = sorted(
            validation_errors,
            key=lambda issue: (
                0 if issue.get("type") == "browser_status" else 1,
                0 if issue.get("severity") == "blocker" else 1,
            ),
        )

        regeneration_context = {
            "source": "validation",
            "errors": prioritized_errors,
            "primary_runtime_issue": (
                prioritized_errors[0] if prioritized_errors else {}
            ),

            # Runtime validation の実測結果を Repair V2 に渡す
            "stdout": validation_stdout,
            "stderr": validation_stderr,

            "available_php_files": available_php_files or [],

            # Deploy 成功/失敗の情報と Runtime validation の情報を混同しない
            "deploy_evidence": deploy_evidence or {},
            "deploy_diagnosis": deploy_diagnosis or {},

            # Browser / PHP lint など、今回の修正対象を決める実測結果
            "validation_evidence": {
                "stdout": validation_stdout,
                "stderr": validation_stderr,
                "errors": validation_errors,
            },

            "contract_feedback": contract_feedback,
            "deployment_contract": deployment_contract or {},
        }

        regenerated = regenerate_file_with_context(
            target_file,
            architecture,
            regeneration_context,
            rules,
            task_rules,
            format_rules,
        )

        if regenerated is None:
            print(f"Repair did not modify {target_file}.")
            continue

        regenerated = postprocess_regenerated_file_content(
            regenerated,
            target_file,
        )

        print(
            "===== REGENERATE regenerate_file_with_context RETURN CHECK ====="
        )
        print(type(regenerated))
        print(repr(regenerated[:100]) if regenerated else regenerated)

        if regenerated is None:
            raise RuntimeError(
                f"Regeneration returned None: {target_file}"
            )

        safe_write_file(
            safe_root,
            target_file,
            regenerated,
        )

        repaired_files[target_file] = regenerated

        print("AFTER WRITE")
        print("===== FILE AFTER WRITE =====")
        print(
            (safe_root / target_file).read_text(
                encoding="utf-8"
            )[:600]
        )

        print("Repair completed.")

    return repaired_files

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
    """Run deploy, collect evidence, determine success, and analyze failures.

    Returns:
        (deploy_result, deploy_evidence, deploy_diagnosis, deploy_success)

    Success is determined from deterministic deployment evidence.
    Root Cause Analysis is used only when deployment is not successful.
    """

    deploy_result = deploy_pipeline()
    deploy_evidence = collect_deploy_evidence()

    # =========================================================
    # 1. Determine deploy success from actual execution results
    # =========================================================

    return_code = deploy_result.get("return_code")
    if return_code is None:
        return_code = 0 if deploy_result.get("success") else 1

    deploy_success = (return_code == 0)

    # =========================================================
    # 2. Successful deployment does not require RCA
    # =========================================================

    if deploy_success:
        deploy_diagnosis = {
            "category": "deployment",
            "root_cause": "none",
            "reason": "Deployment completed successfully.",
            "confidence": 1.0,
        }

        return (
            deploy_result,
            deploy_evidence,
            deploy_diagnosis,
            True,
        )

    # =========================================================
    # 3. Deployment failed -> determine Root Cause
    # =========================================================

    error_text = (
        str(deploy_result.get("stdout", ""))
        + "\n"
        + str(deploy_result.get("stderr", ""))
    )

    # ---------------------------------------------------------
    # Known Podman error:
    # A container attached to an existing pod cannot define
    # published ports itself when the pod shares the network.
    # The port binding must be defined when the pod is created.
    # ---------------------------------------------------------
    if (
        "published or exposed ports must be defined when the pod is created"
        in error_text
        and
        "network cannot be configured when it is shared with a pod"
        in error_text
    ):
        deploy_diagnosis = {
            "category": "container",
            "root_cause": "pod_port_configuration",
            "reason": (
                "The php container is attached to a shared-network pod, "
                "but its published port is defined on the container instead "
                "of the pod. Podman requires the port binding to be defined "
                "when the pod is created."
            ),
            "confidence": 0.99,
            "repair_hint": (
                "Move the web port publish configuration from "
                "containers.podman.podman_container to "
                "containers.podman.podman_pod in ansible/playbook.yml."
            ),
            "repair_target": "ansible/playbook.yml",
        }

    else:
        # -----------------------------------------------------
        # Unknown deployment failure -> perform normal RCA
        # -----------------------------------------------------
        deploy_diagnosis = analyze_deploy_error(
            deploy_result,
            deploy_evidence,
        )

    # =========================================================
    # 4. If RCA itself is unavailable, preserve the failure state
    # =========================================================

    if not deploy_diagnosis:
        deploy_diagnosis = {
            "category": "deployment",
            "root_cause": "diagnosis_unavailable",
            "reason": "Deployment failed, but deploy error analysis returned no diagnosis.",
            "confidence": 0.0,
        }

    return (
        deploy_result,
        deploy_evidence,
        deploy_diagnosis,
        False,
    )

def deploy_application_files() -> Tuple[int, str, str]:
    """Application 用 Ansible Playbook を control node に転送して実行する。"""

    local_playbook = PROJECT_ROOT / "ansible" / "application_deploy.yml"
    remote_playbook = (
        "/home/vboxuser/ai_driven/generated/files/ansible/application_deploy.yml"
    )

    print("===== SCP APPLICATION DEPLOY PLAYBOOK =====")

    scp_code, scp_stdout, scp_stderr = run_command([
        "scp",
        str(local_playbook),
        f"{ANSIBLE_CONTROL_NODE}:{remote_playbook}",
    ])

    if scp_code != 0:
        return scp_code, scp_stdout, scp_stderr

    print("===== RUN APPLICATION ANSIBLE =====")

    return run_remote_command(
        ANSIBLE_CONTROL_NODE,
        "cd /home/vboxuser/ai_driven/generated/files && "
        "ansible-playbook "
        "-i ansible/inventory.ini "
        "ansible/application_deploy.yml",
    )


# =========================================================
# main()
# =========================================================

def run_infrastructure_pipeline(context: Dict[str, Any], task_name: str, task: str) -> bool:
    deploy_result = {}
    deploy_evidence = {}
    deploy_diagnosis = {}
    browser_issues: List[Dict[str, Any]] = []
    lint_issues: List[Dict[str, Any]] = []

    data, raw_output = generate_initial_data(
        context,
        task_name,
        task,
    )

    data, review_data = review_loop(data, context)

    # =========================================================
    # Deterministic Infrastructure Contract Validation
    # =========================================================
    if context.get("task_type") == "infrastructure":
        playbook_files = [
            f
            for f in data.get("files", [])
            if f.get("path") == "ansible/playbook.yml"
        ]

        if len(playbook_files) != 1:
            raise RuntimeError(
                "Infrastructure Generate must contain exactly "
                "one ansible/playbook.yml."
            )

        playbook_content = playbook_files[0].get("content", "")

        try:
            parsed_playbook = yaml.safe_load(playbook_content)
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"Generated infrastructure playbook is invalid YAML: {e}"
            ) from e

        validate_infrastructure_playbook_contract(
            parsed_playbook
        )

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
    validation_success = False
    for attempt in range(MAX_VALIDATION_RETRY):
        print(f"\n===== VALIDATION ATTEMPT {attempt + 1} =====")

        static_validation_errors: List[Dict[str, Any]] = []

        try:
            if not playbook_file.exists():
                static_validation_errors.append({
                    "type": "missing_playbook",
                    "file": str(playbook_file)
                })
            else:
                playbook_text = playbook_file.read_text(encoding="utf-8")
                parsed_playbook = yaml.safe_load(playbook_text)

                if not isinstance(parsed_playbook, list):
                    static_validation_errors.append({
                        "type": "ansible_playbook_structure",
                        "file": str(playbook_file),
                        "stderr": (
                            "Playbook root must be a YAML list. "
                            "Ansible playbooks must use a list of plays at the root."
                        )
                    })
                else:
                    for index, play in enumerate(parsed_playbook):
                        if not isinstance(play, dict):
                            static_validation_errors.append({
                                "type": "ansible_playbook_structure",
                                "file": str(playbook_file),
                                "stderr": (
                                    f"Play at index {index} must be a mapping."
                                )
                            })
                            continue

                        if "hosts" not in play:
                            static_validation_errors.append({
                                "type": "ansible_playbook_structure",
                                "file": str(playbook_file),
                                "stderr": (
                                    f"Play at index {index} is missing 'hosts'."
                                )
                            })

                        if "tasks" not in play:
                            static_validation_errors.append({
                                "type": "ansible_playbook_structure",
                                "file": str(playbook_file),
                                "stderr": (
                                    f"Play at index {index} is missing 'tasks'."
                                )
                            })
                        elif not isinstance(play["tasks"], list):
                            static_validation_errors.append({
                                "type": "ansible_playbook_structure",
                                "file": str(playbook_file),
                                "stderr": (
                                    f"'tasks' at play index {index} must be a list."
                                )
                            })

            if not inventory_file.exists():
                static_validation_errors.append({
                    "type": "missing_inventory",
                    "file": str(inventory_file)
                })
            else:
                inventory_text = inventory_file.read_text(encoding="utf-8")
                if "asbsvr" not in inventory_text or "rockey8" not in inventory_text:
                    static_validation_errors.append({
                        "type": "invalid_inventory",
                        "file": str(inventory_file),
                        "stderr": "Inventory format is invalid."
                    })

            if not php_file.exists():
                static_validation_errors.append({
                    "type": "missing_php",
                    "file": str(php_file)
                })

        except Exception as e:
            static_validation_errors.append({
                "type": "yaml_parse",
                "file": str(playbook_file),
                "stderr": str(e)
            })

        runtime_validation_errors, stdout, stderr = run_validation(
            SAFE_ROOT,
            inventory_file,
            playbook_file,
            php_file
        )

        validation_errors = static_validation_errors + runtime_validation_errors

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
            context["task_rules"],
            context["format_rules"],
            SAFE_ROOT,
            deployment_contract=context.get("deployment_contract", {}),
        )

    if not validation_success:
        print("\nValidation failed. Deployment will not start.")
        print(json.dumps(validation_errors, indent=2, ensure_ascii=False))
        return False

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

        # Remote validation error を Infrastructure Repair に渡す
        #
        # Remote Validation の生ログを最優先の証拠として扱う。
        # LLM reviewer の diagnosis は Remote Validation の実エラーより
        # 優先してはいけない。
        remote_error_text = (
            str(stdout or "")
            + "\n"
            + str(stderr or "")
        )

        remote_diagnosis = {}

        if "argument 'env' is of type" in remote_error_text:
            remote_diagnosis = {
                "category": "ansible",
                "root_cause": "invalid_env_type",
                "reason": (
                    "The containers.podman.podman_container module "
                    "received env as a list, but this module requires "
                    "a mapping/dictionary."
                ),
                "confidence": 1.0,
                "repair_hint": (
                    "Change env from list syntax to mapping syntax. "
                    "For example: "
                    "env:\\n"
                    "  MYSQL_ROOT_PASSWORD: secret"
                ),
                "repair_target": "ansible/playbook.yml",
            }

        regeneration_context = {
            "source": "remote_validation",
            "errors": remote_errors,
            "stdout": stdout,
            "stderr": stderr,
            "validation_evidence": {
                "stdout": stdout,
                "stderr": stderr,
                "raw_remote_stdout": stdout,
                "raw_remote_stderr": stderr,
                "raw_remote_error_text": remote_error_text,
                "errors": remote_errors,
            },
            "deploy_diagnosis": remote_diagnosis,
            "contract_feedback": "",
        }

        repair_target = "ansible/playbook.yml"

        print(f"===== REMOTE VALIDATION REPAIR: {repair_target} =====")

        repair_attempts = 2
        regenerated = None

        for repair_attempt in range(repair_attempts):
            try:
                print(
                    f"\n===== REGENERATE {repair_target} "
                    f"USING AI (auto-repair {repair_attempt + 1}/{repair_attempts}) ====="
                )

                regenerated = regenerate_file_with_context(
                    repair_target,
                    context["architecture"],
                    regeneration_context,
                    context["rules"],
                    context["task_rules"],
                    context["format_rules"],
                )

                if regenerated is None:
                    raise RuntimeError(
                        f"Regeneration returned None: {repair_target}"
                    )

                safe_write_file(
                    SAFE_ROOT,
                    repair_target,
                    regenerated,
                )

                print(
                    "Regenerated file written to SAFE_ROOT:",
                    repair_target,
                )

                break

            except Exception as e:
                print(
                    f"Auto-repair attempt {repair_attempt + 1} failed: {e}"
                )

                if repair_attempt >= repair_attempts - 1:
                    raise RuntimeError(
                        f"Deploy auto repair failed while regenerating "
                        f"{repair_target}: {e}"
                    ) from e

                regeneration_context["contract_feedback"] = str(e)

                print(
                    "Retrying auto-repair with deterministic "
                    "contract feedback..."
                )

        if regenerated is None:
            raise RuntimeError(
                f"Remote validation repair returned None: {repair_target}"
            )

        # regenerate_file_with_context() の返却値は、
        # 「ファイル本文」または「JSON形式の再生成レスポンス」の可能性がある。
        # 必ずファイル本文へ正規化してから後処理する。

# Repair v2 already returns the complete repaired file content.
# Do not interpret it as a generated-file JSON response.

        safe_write_file(
            SAFE_ROOT,
            repair_target,
            regenerated,
        )

        print(
            f"Regenerated file written to SAFE_ROOT: {repair_target}"
        )

        print("===== SCP REPAIRED FILES TO ANSIBLE CONTROL NODE =====")
        run_command([
            "scp",
            "-r",
            str(SAFE_ROOT),
            f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
        ])

        print("===== REMOTE PLAYBOOK CHECK AFTER REPAIR =====")
        repaired_remote_playbook = run_remote_command(
            ANSIBLE_CONTROL_NODE,
            "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml",
        )

        if isinstance(repaired_remote_playbook, dict):
            print(
                repaired_remote_playbook.get("stdout", "")
            )
        else:
            print(repaired_remote_playbook)

        print("===== REMOTE VALIDATION AFTER REPAIR =====")
        remote_errors, stdout, stderr = run_remote_validation()

        if remote_errors:
            print("Remote validation failed after repair")
            for e in remote_errors:
                print(e)
            raise RuntimeError(
                "Remote validation failed after repair"
            )

        if remote_errors:
            print("Remote validation failed after repair")
            for e in remote_errors:
                print(e)
            raise RuntimeError("Remote validation failed after repair")

    
    deploy_success = False

    if validation_success:
        print("\nValidation passed")
        print(playbook_file.read_text())

        deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = (
            perform_deploy_cycle()
        )

        # Deployment succeeded at the command level.
        # Confirm the actual Pod state before browser/PHP validation.
        pod_state = check_pod_state()
        deploy_evidence["pod_state"] = pod_state

        if not pod_state["pod_running"]:
            print("Pod is not running after deploy")

            deploy_success = False

            deploy_diagnosis = {
                "category": "deployment",
                "root_cause": "pod_not_running",
                "reason": "lamp-pod exists but is not running after deployment.",
                "confidence": 0.99,
                "repair_hint": (
                    "Ensure the deployment starts the existing Pod and its containers."
                ),
                "repair_target": "ansible/playbook.yml",
            }
    else:
        print("\nValidation failed - skip deployment")

    if not deploy_success:
        print("\n===== DEPLOY FAILED - SKIP BROWSER/PHP VALIDATION =====")
    else:
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
                validation_success = deploy_success
                break

            validation_success = False

            error_list = [
                {
                    "type": issue.get("type", "validation_error"),
                    "file": repair_target,
                    "stderr": issue.get("detail", ""),
                }
                for issue in browser_issues + lint_issues
            ]

            repair_validation_errors(
                error_list,
                browser_result.get("stdout", "") + "\n" + lint_result.get("stdout", ""),
                browser_result.get("stderr", "") + "\n" + lint_result.get("stderr", ""),
                context["architecture"],
                context["rules"],
                context["task_rules"],
                context["format_rules"],
                SAFE_ROOT,
                target_file_override=repair_target,
                deploy_evidence=deploy_evidence,
                deploy_diagnosis=deploy_diagnosis,
                deployment_contract=context.get("deployment_contract", {}),
            )

            print("\n===== SCP TO ANSIBLE CONTROL NODE (after repair) =====")
            run_command([
                "scp",
                "-r",
                str(SAFE_ROOT),
                f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
            ])

            print("\n===== REDEPLOY AFTER REPAIR =====")
            (
                deploy_result,
                deploy_evidence,
                deploy_diagnosis,
                deploy_success,
            ) = perform_deploy_cycle()

            if not deploy_success:
                validation_success = False
                break

            # Re-check actual Pod state after every redeploy.
            pod_state = check_pod_state()
            deploy_evidence["pod_state"] = pod_state

            if not pod_state["pod_running"]:
                print("Pod is not running after redeploy.")

                deploy_success = False
                validation_success = False

                deploy_diagnosis = {
                    "category": "deployment",
                    "root_cause": "pod_not_running",
                    "reason": "lamp-pod exists but is not running after redeployment.",
                    "confidence": 0.99,
                    "repair_hint": (
                        "Ensure the deployment starts the existing Pod and its containers."
                    ),
                    "repair_target": "ansible/playbook.yml",
                }

                break

    if not validation_success and deploy_success:
        combined_issues = browser_issues + lint_issues
        primary_issue = combined_issues[0] if combined_issues else {}
        target = primary_issue.get("repair_target", "src/index.php")
        deploy_diagnosis = {
            "category": primary_issue.get("category", "application"),
            "root_cause": primary_issue.get("type", "browser_validation_failed"),
            "reason": primary_issue.get("detail", "Browser validation or PHP lint failed."),
            "confidence": 0.9,
            "repair_hint": f"Fix {target}.",
            "repair_target": target,
        }

    print("validation_success =", validation_success)
    print("deploy_success =", deploy_success)
    print(json.dumps(deploy_diagnosis, indent=2))

    if deploy_success and validation_success and deploy_diagnosis and deploy_diagnosis.get("root_cause") == "none":
        print("Pipeline completed successfully")
        context["deployment_contract"].update({
            "web_url": "http://192.168.122.10:8080",
            "db_host": "mysql",
            "db_port": 3306,
            "db_name": "testdb",
            "db_user": "root",
            "db_password": "secret",
        })
        return True

    else:
        print("\n=== DEPLOY FAILED DIAGNOSIS ===")
        print(json.dumps(
            deploy_diagnosis,
            indent=2,
            ensure_ascii=False
        ))

        repair_target: Optional[str] = None

        if isinstance(deploy_diagnosis, dict):
            candidate = deploy_diagnosis.get("repair_target")
            if isinstance(candidate, str) and candidate:
                repair_target = candidate

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
                # Deploy failure:
                # First apply deterministic contract repair.
                # Only fall back to AI repair when no deterministic repair applies.
                try:
                    target_path = SAFE_ROOT / repair_target

                    if not target_path.exists():
                        raise RuntimeError(
                            f"Repair target does not exist: {repair_target}"
                        )

                    current_content = target_path.read_text(
                        encoding="utf-8"
                    )

                    deterministic_content = current_content

                    # ====================================================
                    # Deterministic Contract Repair
                    # ====================================================
                    #
                    # Known infrastructure contract violation:
                    # container/pod_name -> name
                    #
                    # Only this exact invalid key is replaced.
                    # All other valid configuration is preserved.
                    # ====================================================

                    if repair_target == "ansible/playbook.yml":
                        deterministic_content = deterministic_content.replace(
                            "container/pod_name: lamp-pod",
                            "name: lamp-pod",
                        )

                        deterministic_content = deterministic_content.replace(
                            "publish_port_map:",
                            "publish:",
                        )

                    if deterministic_content != current_content:
                        print("===== DETERMINISTIC DEPLOY REPAIR =====")
                        print(f"Target: {repair_target}")

                        if "container/pod_name: lamp-pod" in current_content:
                            print(
                                "Replace: container/pod_name: lamp-pod"
                            )
                            print("With:    name: lamp-pod")

                        if "publish_port_map:" in current_content:
                            print(
                                "Replace: publish_port_map:"
                            )
                            print("With:    publish:")

                        safe_write_file(
                            SAFE_ROOT,
                            repair_target,
                            deterministic_content,
                        )

                        print(
                            "===== FILE AFTER DETERMINISTIC DEPLOY REPAIR ====="
                        )
                        print(
                            deterministic_content[:600]
                        )

                        print(
                            "Deterministic deploy repair completed."
                        )

                    else:
                        # ====================================================
                        # AI Repair fallback
                        # ====================================================

                        print(
                            f"===== REGENERATE {repair_target} USING AI ====="
                        )

                        regeneration_context = {
                            "source": "deploy",
                            "errors": [deploy_diagnosis],
                            "stdout": deploy_result.get("stdout", ""),
                            "stderr": deploy_result.get("stderr", ""),
                            "evidence": deploy_evidence,
                            "diagnosis": deploy_diagnosis,
                            "deployment_contract": context.get(
                                "deployment_contract", {}
                            ),
                        }

                        regenerated = regenerate_file_with_context(
                            repair_target,
                            context["architecture"],
                            regeneration_context,
                            context["rules"],
                            context["task_rules"],
                            context["format_rules"],
                        )

                        if regenerated is None:
                            raise RuntimeError(
                                f"Regeneration returned None: {repair_target}"
                            )

                        # ============================================================
                        # Validate AI Repair result before writing/deploying
                        # ============================================================

                        if repair_target == "ansible/playbook.yml":
                            try:
                                parsed_yaml = yaml.safe_load(regenerated)

                                contract_errors = validate_infrastructure_playbook_contract(
                                    parsed_yaml
                                )

                            except Exception as e:
                                contract_errors = [
                                    f"Invalid YAML generated by Repair AI: {e}"
                                ]

                            if contract_errors:
                                print("===== AI REPAIR CONTRACT VIOLATION =====")
                                for error in contract_errors:
                                    print(f"- {error}")

                                # AIが壊した既知のContractを決定的に修正
                                deterministic_repaired = regenerated

                                deterministic_repaired = deterministic_repaired.replace(
                                    "container/pod_name: lamp-pod",
                                    "name: lamp-pod",
                                )

                                # deterministic_repaired = deterministic_repaired.replace(
                                #     "/home/vboxuser/containers/html:/var/www/html",
                                #     "/home/vboxuser/containers/html:/var/www/html:Z",
                                # )

                                deterministic_repaired = deterministic_repaired.replace(
                                    "publish_port_map:",
                                    "publish:",
                                )

                                if deterministic_repaired != regenerated:
                                    print("===== DETERMINISTIC POST-REPAIR FIX =====")

                                    if "publish_port_map:" in regenerated:
                                        print(
                                            "Replace: publish_port_map:"
                                        )
                                        print(
                                            "With:    publish:"
                                        )

                                    if "container/pod_name: lamp-pod" in regenerated:
                                        print(
                                            "Replace: container/pod_name: lamp-pod"
                                        )
                                        print(
                                            "With:    name: lamp-pod"
                                        )

                                    regenerated = deterministic_repaired

                                    # 修正後にもう一度Contract Validator
                                    try:
                                        parsed_yaml = yaml.safe_load(regenerated)
                                        contract_errors = (
                                            validate_infrastructure_playbook_contract(
                                                parsed_yaml
                                            )
                                        )
                                    except Exception as e:
                                        contract_errors = [
                                            f"Invalid YAML after deterministic repair: {e}"
                                        ]

                                if contract_errors:
                                    print("===== REPAIR CONTRACT STILL INVALID =====")
                                    for error in contract_errors:
                                        print(f"- {error}")

                                    raise RuntimeError(
                                        "AI Repair produced an invalid infrastructure "
                                        "playbook contract."
                                    )

                                print("AI Repair result passed after deterministic repair.")
                                
                        safe_write_file(
                            SAFE_ROOT,
                            repair_target,
                            regenerated,
                        )

                        print(
                            f"Regenerated file written to SAFE_ROOT: "
                            f"{repair_target}"
                        )

                except Exception as e:
                    print("Auto-repair regeneration failed:", e)
                    raise RuntimeError(
                        f"Unknown deploy error.\n"
                        f"{deploy_result['stderr']}"
                    )

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
            
            if (
                deploy_success
                and validation_success
                and deploy_diagnosis
                and deploy_diagnosis.get("root_cause") == "none"
            ):
                print("Pipeline completed successfully")
                context["deployment_contract"].update({
                    "web_url": "http://192.168.122.10:8080",
                    "db_host": "mysql",
                    "db_port": 3306,
                    "db_name": "testdb",
                    "db_user": "root",
                    "db_password": "secret",
                })
                return True

        # # Certain diagnosed root causes should trigger an automatic
        # # repair attempt instead of immediately raising an exception.
        # root = deploy_diagnosis.get("root_cause")
        # auto_repair_root_causes = {
        #     "browser_connection_error",
        #     "browser_status",
        #     "pod_not_running",
        #     "apache_not_running",
        #     "container_not_running",
        #     "playbook_error",
        #     "ansible_module_error",
        # }

        # if root in auto_repair_root_causes:
        #     print(f"\n===== AUTO-REPAIR TRIGGERED FOR: {root} =====")

        #     # Perform AI-driven repair of the diagnosed target (e.g. playbook)
        #     file_to_repair = (
        #         deploy_diagnosis.get("repair_target")
        #         or "ansible/playbook.yml"
        #     )

        #     regeneration_context = {
        #         "source": "deploy",
        #         "errors": [deploy_diagnosis],
        #         "stdout": deploy_result.get("stdout", ""),
        #         "stderr": deploy_result.get("stderr", ""),
        #         "evidence": deploy_evidence,
        #         "diagnosis": deploy_diagnosis,
        #     }

        #     repair_attempts = 2
        #     regenerated = None

        #     for repair_attempt in range(repair_attempts):
        #         try:
        #             print(
        #                 f"\n===== REGENERATE {file_to_repair} "
        #                 f"USING AI (auto-repair {repair_attempt + 1}/{repair_attempts}) ====="
        #             )

        #             regenerated = regenerate_file_with_context(
        #                 file_to_repair,
        #                 context["architecture"],
        #                 regeneration_context,
        #                 context["rules"],
        #                 context["task_rules"],
        #                 context["format_rules"],
        #             )

        #             if regenerated is None:
        #                 raise RuntimeError(
        #                     f"Regeneration returned None: {file_to_repair}"
        #                 )

        #             safe_write_file(
        #                 SAFE_ROOT,
        #                 file_to_repair,
        #                 regenerated,
        #             )

        #             print(
        #                 "Regenerated file written to SAFE_ROOT:",
        #                 file_to_repair,
        #             )

        #             break

        #         except Exception as e:
        #             print(
        #                 f"Auto-repair attempt {repair_attempt + 1} failed: {e}"
        #             )

        #             if repair_attempt >= repair_attempts - 1:
        #                 raise RuntimeError(
        #                     f"Deploy auto repair failed while regenerating "
        #                     f"{file_to_repair}: {e}"
        #                 ) from e

        #             print(
        #                 "Retrying auto-repair with deterministic "
        #                 "contract feedback..."
        #             )


        #     # Transfer repaired files to control node and redeploy
        #     print("\n===== SCP TO ANSIBLE CONTROL NODE (auto-repair) =====")
        #     run_command([
        #         "scp",
        #         "-r",
        #         str(SAFE_ROOT),
        #         f"{ANSIBLE_CONTROL_NODE}:/home/vboxuser/ai_driven/generated",
        #     ])

        #     print("===== REMOTE PLAYBOOK CHECK (auto-repair) =====")
        #     print(run_remote_command(
        #         ANSIBLE_CONTROL_NODE,
        #         "cat /home/vboxuser/ai_driven/generated/files/ansible/playbook.yml"
        #     ))

        #     print("\n===== REMOVE OLD POD (auto-repair) =====")
        #     run_remote_command(
        #         EXECUTION_NODE,
        #         "podman pod rm -f lamp-pod || true"
        #     )

        #     print("\n===== REDEPLOY AFTER AUTO-REPAIR =====")
        #     deploy_result, deploy_evidence, deploy_diagnosis, deploy_success = (
        #         perform_deploy_cycle()
        #     )

        #     print("===== PODMAN STATUS AFTER DEPLOY REPAIR =====")
        #     print(run_remote_command(
        #         EXECUTION_NODE,
        #         "podman ps -a"
        #     ))

        #     if not deploy_success:
        #         raise RuntimeError("Deploy failed after auto-repair.")

        #     # ---------------------------------------------------------
        #     # Auto-repair後も、Web/PHPの実動作を再検証する。
        #     #
        #     # Ansibleのreturn code == 0だけでは、
        #     # Webアプリケーションが正常とは判断しない。
        #     # ---------------------------------------------------------
        #     print("\n===== POST-REPAIR BROWSER VALIDATION =====")
        #     browser_result = run_browser_validation()
        #     browser_issues = analyze_browser_validation(browser_result)

        #     print(json.dumps(
        #         browser_result,
        #         indent=2,
        #         ensure_ascii=False,
        #     ))

        #     print(
        #         "Browser issues:",
        #         json.dumps(browser_issues, ensure_ascii=False)
        #     )

        #     print("\n===== POST-REPAIR PHP LINT =====")
        #     lint_result = run_php_lint()
        #     lint_issues = analyze_php_lint_result(lint_result)

        #     print(json.dumps(
        #         lint_result,
        #         indent=2,
        #         ensure_ascii=False,
        #     ))

        #     print(
        #         "PHP lint issues:",
        #         json.dumps(lint_issues, ensure_ascii=False)
        #     )

        #     # ---------------------------------------------------------
        #     # Web/PHPともに正常なら初めて成功。
        #     # ---------------------------------------------------------
        #     if not browser_issues and not lint_issues:
        #         print("Pipeline completed successfully after auto-repair")

        #         context["deployment_contract"].update({
        #             "web_url": "http://192.168.122.10:8080",
        #             "db_host": "mysql",
        #             "db_port": 3306,
        #             "db_name": "testdb",
        #             "db_user": "root",
        #             "db_password": "secret",
        #         })

        #         return True

        #     # ---------------------------------------------------------
        #     # Deploy自体は成功したが、実動作検証に失敗した。
        #     # ここで成功扱いしてはいけない。
        #     # ---------------------------------------------------------
        #     print("\n=== POST-REPAIR VALIDATION FAILED ===")

        #     combined_issues = browser_issues + lint_issues
        #     primary_issue = combined_issues[0] if combined_issues else {}

        #     deploy_diagnosis = {
        #         "category": primary_issue.get(
        #             "category",
        #             "infrastructure"
        #         ),
        #         "root_cause": primary_issue.get(
        #             "type",
        #             "post_repair_validation_failed"
        #         ),
        #         "reason": primary_issue.get(
        #             "detail",
        #             "Post-repair browser or PHP validation failed."
        #         ),
        #         "confidence": 0.99,
        #         "repair_hint": (
        #             f"Fix {primary_issue.get('repair_target', repair_target)}."
        #         ),
        #         "repair_target": primary_issue.get(
        #             "repair_target",
        #             repair_target
        #         ),
        #     }

            # raise RuntimeError(
            #     "Deploy completed but post-repair validation failed."
            # )
        raise RuntimeError("Deploy failed")

def review_application(
    data: Dict[str, Any],
    task_name: str,
    task: str,
    rules: str,
    review_rules: str,
    task_review_rules: str,
    reviewer_prompt: str,
) -> Dict[str, Any]:

    print("\n===== APPLICATION REVIEW START =====")

    review_prompt = f"""
Task Name:
{task_name}

Task:
{task}

Project Rules:
{rules}

Review Rules:
{review_rules}

Application Review Rules:
{task_review_rules}

Generated Files:
{json.dumps(data.get("files", []), indent=2, ensure_ascii=False)}

Review the generated files according to the supplied Task, Project Rules,
Review Rules, and Application Review Rules.

Return JSON only.
"""

    raw = ollama_chat(
        messages=[
            {
                "role": "system",
                "content": reviewer_prompt,
            },
            {
                "role": "user",
                "content": review_prompt,
            },
        ],
        temperature=0.0,
        num_predict=2048,
        think=False,
    )

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
) -> bool:

    print("\n===== APPLICATION PIPELINE START =====")

    data, raw_output = generate_initial_data(
        context,
        task_name,
        task,
    )

    print("\n===== APPLICATION REVIEW START =====")
    review_result = review_application(
        data,
        task_name,
        task,
        context.get("rules", ""),
        context.get("review_rules", ""),
        context.get("task_review_rules", ""),
        context.get("reviewer_prompt", "")
    )
    if not review_result.get("approved", False):
        print("Application review failed.")
        return False
    print("\n===== APPLICATION REVIEW END =====")

    print("\n===== APPLICATION GENERATE COMPLETE =====")

    print("Generated files:")
    for file in data.get("files", []):
        print("-", file.get("path"))


    # Persist generated files to SAFE_ROOT so we can validate them locally.

    print(f"APPLICATION ALLOWED PATHS = {sorted(ALLOWED_PATHS | APPLICATION_ALLOWED_PATHS)}")

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
                    context["task_rules"],
                    context["format_rules"],
                    SAFE_ROOT,
                    available_php_files=available_files,
                    deployment_contract=context.get("deployment_contract", {}),
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
            context["task_rules"],
            context["format_rules"],
            SAFE_ROOT,
            deployment_contract=context.get("deployment_contract", {}),
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

        print("===== APPLICATION ANSIBLE DEPLOY =====")
        try:
            deploy_code, deploy_stdout, deploy_stderr = deploy_application_files()

            print(deploy_stdout)

            if deploy_stderr:
                print(deploy_stderr)

            if deploy_code != 0:
                print("Application Ansible deploy failed.")
                return False

        except Exception as e:
            print("Application Ansible deploy failed:", e)
            return False


        print("\n===== BROWSER VALIDATION (application pipeline) =====")
        try:
            browser_result = run_browser_validation()
            print(json.dumps(browser_result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Browser validation failed:", e)
            return False

        print("\n===== PHP LINT (application pipeline) =====")
        try:
            lint_result = run_php_lint()
            print(json.dumps(lint_result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("PHP lint (remote) failed:", e)
            return False

    else:
        print("Skipping deploy: PHP validation did not succeed.")
        return False

    print("\n===== APPLICATION PIPELINE END =====")
    return True


def main() -> None:
    task_handlers = {
        "infrastructure": run_infrastructure_pipeline,
        "application": run_application_pipeline,
    }

    shared_context = None

    for task_name in TASK_SEQUENCE:
        task = load_task(task_name)
        task_type = Path(task_name).stem
        handler = task_handlers.get(task_type)

        if handler is None:
            print(f"\n===== SKIP TASK: {task_name} (not implemented) =====")
            continue

        print(f"\n===== RUN TASK: {task_name} =====")

        context = load_context(task_type,previous_context=shared_context,)

        success = handler(context, task_name, task)

        if success is False:
            print(
                f"\n===== STOP PIPELINE: {task_type} FAILED ====="
            )
            break

        shared_context = context


if __name__ == "__main__":
    main()
