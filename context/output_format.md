# AI Output Format

Return valid JSON only.

Required top-level fields:

- summary
- files
- commands
- risks

Each files entry:

- path
- content

Paths must be relative to SAFE_ROOT.

Do not include generated/, absolute Windows paths, or absolute Linux paths.

The entire response must be parseable by Python json.loads().

Content must be valid JSON strings.
Escape backslashes, quotes, and newlines according to JSON rules.
Do not add unnecessary backslashes.

When content contains source code, the content value is a JSON string.

All backslashes in source code MUST be escaped according to JSON syntax.

Example:
PHP source:
new \PDO()

JSON representation:
"new \\PDO()"

The complete response MUST be valid JSON and parseable by Python json.loads().
