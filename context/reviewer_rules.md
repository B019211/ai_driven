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

```json
{
  "severity": "BLOCKING"
}
```
