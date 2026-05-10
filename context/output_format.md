# AI Output Format

AI must always return valid JSON.

Required structure:

```json
{
  "summary": "",
  "files": [
    {
      "path": "",
      "content": ""
    }
  ],
  "commands": [],
  "risks": []
}
```

Rules:

- JSON only
- No markdown
- No explanations outside JSON
- File paths must be relative
- Generated code must be deployable

```

```
