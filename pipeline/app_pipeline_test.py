import sys
from pathlib import Path

# Ensure pipeline directory is on sys.path when executed from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_pipeline


def main() -> None:
    # context = ai_pipeline.load_context()
    # task_name = "application.md"
    # task = ai_pipeline.load_task(task_name)

    # ai_pipeline.run_application_pipeline(context, task_name, task)

    task_handlers = {
        "application": ai_pipeline.run_application_pipeline,
    }

    task_name = "application.md"
    task = ai_pipeline.load_task(task_name)
    task_type = Path(task_name).stem
    handler = task_handlers.get(task_type)

    if handler is None:
        print(f"\n===== SKIP TASK: {task_name} (not implemented) =====")
        return

    print(f"\n===== RUN TASK: {task_name} =====")

    context = ai_pipeline.load_context(task_type)
    
    context["deployment_contract"].update({
        "web_url": "http://192.168.122.10:8080",
        "db_host": "mysql",
        "db_port": 3306,
        "db_name": "testdb",
        "db_user": "root",
        "db_password": "secret",
    })

    handler(context, task_name, task)



if __name__ == "__main__":
    main()
