# System Rules

## Core Constraints

- Use Podman only.
- Use Ansible for deployment.
- Do not use Docker.
- Do not generate destructive commands.
- Do not generate markdown or explanatory prose.
- Use UTF-8.
- Generate only the files requested by the task.
- Do not leave file content empty.

## Ansible Rules

- Use hosts: execution.
- Do not use hosts: all.
- Prefer Ansible modules over shell.
- Prefer containers.podman modules.
- Keep playbooks idempotent.
- Do not use timeout for containers.podman.podman_pod.
- Do not use unsupported parameters.
- playbook.yml must include a copy task.
- Copy generated/files/src/index.php to /home/vboxuser/containers/html/index.php.
- Use

  copy:
  src: "{{ playbook_dir }}/../src/index.php"
  dest: /home/vboxuser/containers/html/index.php

- The existing Podman tasks are already correct.
- Do NOT redesign the playbook.
- Only add ONE Ansible copy task after the containers are created.
- Do not modify any existing podman_pod or podman_container tasks.

- The playbook is invalid if this task is missing.

## Podman Rules

- Use podman_pod for the pod.
- Use podman_container for containers.
- Publish ports only through podman_pod.publish.
- Do not use shell-based Podman commands when a module exists.
- The existing Podman deployment tasks are considered validated.

Do not modify:

- podman_pod
- podman_container

- unless the validation error explicitly points to those tasks.
- Only append additional tasks after them.

## Validation Rule

- If validation reports unsupported parameters, remove them and regenerate the affected file.
  When fixing validation errors:
- Fix ONLY the validation error.
- Do NOT rewrite the whole playbook.
- Keep every valid line unchanged.
- Return the complete corrected file.
- Only modify the task directly related to the reported validation error.
- Preserve every existing task exactly.
