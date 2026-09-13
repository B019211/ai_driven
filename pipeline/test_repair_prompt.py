import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_pipeline


# def capture_ollama_chat(messages, temperature=0.0, num_predict=4096, think=False):
#     print()
#     print("=" * 100)
#     print("===== SYSTEM PROMPT =====")
#     print("=" * 100)
#     print(messages[0]["content"])

#     print()
#     print("=" * 100)
#     print("===== USER PROMPT =====")
#     print("=" * 100)
#     print(messages[1]["content"])

#     print()
#     print("=" * 100)
#     print("===== PROMPT CAPTURE FINISHED =====")
#     print("=" * 100)

#     # raise RuntimeError("OLLAMA CALL BLOCKED BY TEST")

original_ollama_chat = ai_pipeline.ollama_chat


def capture_ollama_chat(
    messages,
    temperature=0.0,
    num_predict=4096,
    think=False,
):
    print("\n" + "=" * 100)
    print("===== SYSTEM PROMPT =====")
    print("=" * 100)
    print(messages[0]["content"])

    print("\n" + "=" * 100)
    print("===== USER PROMPT =====")
    print("=" * 100)
    print(messages[1]["content"])

    print("\n" + "=" * 100)
    print("===== CALLING REAL OLLAMA =====")
    print("=" * 100)

    raw = original_ollama_chat(
        messages=messages,
        temperature=temperature,
        num_predict=num_predict,
        think=think,
    )

    print("\n" + "=" * 100)
    print("===== RAW OLLAMA RESULT =====")
    print("=" * 100)
    print(repr(raw))

    print("\n" + "=" * 100)
    print("===== RAW OLLAMA RESULT (TEXT) =====")
    print("=" * 100)
    print(raw)

    # IMPORTANT:
    # Do not allow the test to continue into file regeneration/write.
    raise RuntimeError(
        "TEST STOP: Ollama response captured; repaired file was NOT written."
    )

ai_pipeline.ollama_chat = capture_ollama_chat


context = ai_pipeline.load_context("infrastructure")

target_file = ai_pipeline.SAFE_ROOT / "ansible" / "playbook.yml"

current_file = target_file.read_text(encoding="utf-8")

import yaml

parsed_yaml = yaml.safe_load(current_file)

validation_messages = ai_pipeline.validate_infrastructure_playbook_contract(
    parsed_yaml
)

validation_errors = []

for message in validation_messages:
    validation_errors.append(
        {
            "type": "contract_violation",
            "file": "ansible/playbook.yml",
            "stderr": message,
        }
    )

validation_stderr = "\n".join(validation_messages)

deploy_evidence = {
    "contract_feedback": validation_stderr,
}

deploy_diagnosis = {
    "category": "contract",
    "root_cause": "contract_violation",
    "reason": "Infrastructure contract validation failed.",
    "confidence": 1.0,
}

contract_feedback = validation_stderr

deployment_contract = context.get("deployment_contract", {})


print()
print("===== CONTRACT VALIDATION RESULT =====")

if validation_errors:
    for error in validation_errors:
        print(error["stderr"])
else:
    print("No contract violations found.")

print()
print("===== START REPAIR PROMPT CAPTURE =====")

if not validation_errors:
    raise RuntimeError(
        "No contract violations found in the current playbook. "
        "The prompt capture test cannot reproduce a repair case."
    )

try:
    ai_pipeline.repair_validation_errors(
        validation_errors,
        "",
        validation_stderr,
        context["architecture"],
        context["rules"],
        context["task_rules"],
        context["format_rules"],
        ai_pipeline.SAFE_ROOT,
        target_file_override="ansible/playbook.yml",
        deploy_evidence=deploy_evidence,
        deploy_diagnosis=deploy_diagnosis,
        contract_feedback=contract_feedback,
        deployment_contract=deployment_contract,
    )

except RuntimeError as e:
    print()
    print("===== TEST FINISHED =====")
    print(str(e))