from pathlib import Path

architecture = Path(
"context/architecture.md"
).read_text(encoding="utf-8")

print(architecture)
