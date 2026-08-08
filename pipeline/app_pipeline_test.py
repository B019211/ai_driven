import sys
from pathlib import Path

# Ensure pipeline directory is on sys.path when executed from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_pipeline


def main() -> None:
    context = ai_pipeline.load_context()
    task_name = "application.md"
    task = ai_pipeline.load_task(task_name)

    ai_pipeline.run_application_pipeline(context, task_name, task)


if __name__ == "__main__":
    main()
