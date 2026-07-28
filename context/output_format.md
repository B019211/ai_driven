# AI Output Format

Return JSON only.

Required fields:

- summary
- files
- commands
- risks

Each file entry must contain:

- path
- content

Rules:

- Do not omit required fields.
- Do not generate extra files beyond the required set.
