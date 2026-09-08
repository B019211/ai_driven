# Review Rules

Review for pipeline viability, not perfect production quality.

Approve when no blocking problem exists.

Reject only when the artifact:

- breaks the pipeline
- exposes secrets beyond the explicitly defined learning-environment values
- contains destructive actions
- uses unsupported parameters
- has a clear syntax or configuration failure
- violates an explicit task rule
- violates a task-specific review rule

Allow temporary local-learning compromises when the pipeline can proceed.

## Review Responsibility

Review evaluates whether the generated artifact is acceptable before validation and execution.

Review must identify blocking structural problems when they are visible from the generated artifact.

Validation remains responsible for deterministic machine-checkable validation.

Do not approve an artifact that is clearly structurally invalid merely because the failure would later be detected by validation.

## Root Cause

When diagnosis is required:

- identify the actual observed problem
- do not guess
- do not report a downstream symptom as the root cause when the upstream artifact is already invalid

## Repair

During repair:

- preserve valid existing content
- change only what is necessary to resolve the reported problem
- do not rewrite unrelated content
- do not redesign the system
- required missing structure may be added
- return the complete corrected file

Warnings are for non-blocking issues.

Blocking problems must be represented as:

{
"severity": "BLOCKING"
}

## Diagnosis

- diagnosis MUST be a single JSON object.
- Do NOT return diagnosis as an array.
- diagnosis represents the primary/root cause of the review result.
- category must be one of:
  application, deployment, configuration, infrastructure.
- root_cause must be a string.
- reason must be a string.
- confidence must be a number between 0 and 1.
- Do not use percentage values such as 95.

Before deciding approved, check every Blocking Problem listed in the Task Review Rules against the generated artifact.

If any Blocking Problem is present:

- approved must be false.
- risks must include a risk with severity "BLOCKING".
- diagnosis.root_cause must describe the observed blocking problem.

If no Blocking Problem is present:

- approved may be true.

## Artifact Fact Verification

Artifact Facts are machine-verified observations of the generated artifact.
Use them when determining whether an element is present or absent.
Do not report an element as missing when Artifact Facts show that it exists.

Before reporting a blocking problem, verify the claimed problem against the actual Generated JSON artifact.

Do not report a missing key, value, task, file, or configuration when it is present in the generated artifact.

For infrastructure reviews:

- Inspect ansible/playbook.yml directly.
- Verify the actual play structure before reporting configuration problems.
- A play targeting the execution group must contain hosts: execution.
- Do not infer that hosts is missing from formatting, indentation, or abbreviated inspection.
- Do not report a Jinja syntax problem unless an actual Jinja expression is present in the generated artifact.

When a blocking problem is reported:

- The diagnosis must describe an actual observed problem in the artifact.
- The reviewer must be able to identify the corresponding location in the artifact.
- Do not create a blocking problem from an assumption or inferred structure.
- Apply only the contract that is authoritative for the current task type.
- Do not apply application-level requirements to an infrastructure review
  unless the infrastructure task explicitly requires those application-level
  requirements.
- Do not treat requirements defined only for the application task as
  infrastructure artifact requirements.

  ## Output

Review result MUST contain the following top-level keys:

- approved
- summary
- risks
- diagnosis

summary must be a short description of the review result.

approved must be a boolean.

risks must contain the identified review risks.

diagnosis must be a single JSON object as defined in the Diagnosis section.
