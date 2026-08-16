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
- Copy ../src/index.php to /home/vboxuser/containers/html/index.php.
- Use

  copy:
  src: "{{ playbook_dir }}/../src/index.php"
  dest: /home/vboxuser/containers/html/index.php

- The existing Podman tasks are already correct.
- Do NOT redesign the playbook.
- Only add ONE Ansible copy task after the containers are created.
- Do not modify any existing podman_pod or podman_container tasks.

- The playbook is invalid if this task is missing.

Ansibleのcopyモジュールでsrc/index.phpをリモートホストへ配置する。

重要な制約:

- playbook.ymlは ansible/ に配置される。
- index.phpは src/ に配置される。
- したがってcopy.srcは必ず "../src/index.php" とする。
- copy.destは "/home/vboxuser/containers/html/index.php" とする。
- copyタスクでは owner と group を指定してはならない。
- リモート側の既存ユーザー/グループ所有権を変更しない。
- modeのみ必要に応じて指定し、"0644" とする。
- srcを "src/index.php" に戻してはならない。

【Infrastructure固定ルール】
playbook.ymlと生成対象ファイルの配置関係を変更してはならない。

d:/Devlopment/ai_driven/generated/files/
├── ansible/
│ ├── inventory.ini
│ └── playbook.yml
└── src/
└── index.php

playbook.ymlからsrc/index.phpを参照する場合:
src: ../src/index.php

禁止:

- src: src/index.php
- src: files/src/index.php

index.phpのcopyではowner/groupを指定禁止。

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
