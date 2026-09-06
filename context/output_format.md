# AI Output Format

Return exactly one valid JSON object.

The top-level object must contain exactly these keys:

- summary
- files
- commands
- risks

Each files item must contain exactly these keys:

- path
- content

Do not use ansible, src, or inventory as top-level keys.

Paths must be relative to SAFE_ROOT.

Do not include:

- generated/
- absolute Windows paths
- absolute Linux paths

The complete response must be parseable by Python `json.loads()`.

Source code must be represented as a JSON string.

Escape characters according to standard JSON syntax.

Do not add explanatory prose, Markdown, or code fences outside the JSON object.
