# Infrastructure Task

Create a runnable Podman LAMP environment.

Required files:

- ansible/playbook.yml
- ansible/inventory.ini
- src/index.php

Requirements:

- use lamp-pod
- publish 8080:80
- mount /home/vboxuser/containers/html
- deploy src/index.php to /home/vboxuser/containers/html/index.php
- PHP must provide PDO MySQL
- browser must display index.php

Completion:

- YAML validation passes
- deployment succeeds
- browser validation succeeds

infrastructureのPHP検証ページはDB接続を行わない。
src/index.php は Infrastructure OK の表示だけを行う。
