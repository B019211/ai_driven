# Review Rules

Review for pipeline viability rather than perfect production hygiene.

Reject when:

- the artifact clearly breaks the pipeline
- secrets or destructive actions are exposed
- unsupported module parameters are used
- podman_pod.state is not started
- podman_container contains ports
- container environment uses environment instead of env
- the web container mounts to a path other than /var/www/html
- the database container name is not mysql
- shell-based Podman management is used when a containers.podman module exists
- Reject if the playbook does not deploy src/index.php to /home/vboxuser/containers/html/index.php

Allow temporary, local-learning compromises when the pipeline can still proceed.

Playbookに以下が存在しない場合はレビューをRejectすること。

- Podman Pod作成
- PHPコンテナ作成
- MySQLコンテナ作成
- src/index.php を /home/vboxuser/containers/html/index.php へ配置する copy または同等のタスク

Never approve a playbook if:

Reject if:

- Unsupported Ansible module parameters are used.
- Unsupported Podman module parameters are introduced.
- Existing Podman tasks are modified without necessity.
- Existing validated tasks are rewritten.
- The review must reject any playbook that invents module parameters.
