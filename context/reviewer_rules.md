# Review Rules

Review for pipeline viability, not perfect production quality.

Approve when no blocking problem exists.

Reject only when the artifact:

- breaks the pipeline
- exposes secrets or destructive actions
- uses unsupported parameters
- has a clear syntax/configuration failure
- violates an explicit task or task-review rule

Allow temporary local-learning compromises when the pipeline can proceed.

During repair:

- preserve valid existing content
- change only the reported problem
- do not rewrite unrelated content
- return the complete corrected file

Warnings are for non-blocking issues.
