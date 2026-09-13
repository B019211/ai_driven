# Infrastructure Generation Rules

## Scope

Generate only:

ansible/playbook.yml

Do not generate:

- ansible/inventory.ini
- src/index.php
- Dockerfile
- Containerfile

## Ansible Structure

The generated playbook MUST:

- be valid YAML
- have a list as the root
- target the execution host
- contain tasks directly under the play
- use separate tasks for the pod, PHP container, MySQL container, and index.php copy

Do not use a top-level playbook object.

## Podman

Use exactly these Ansible modules:

containers.podman.podman_pod
containers.podman.podman_container

For containers.podman.podman_pod:

container/pod name key MUST be name
pod name MUST be lamp-pod
state MUST be started
port publication key MUST be publish
published port MUST be "8080:80"

For containers.podman.podman_container:

container name key MUST be name
PHP name MUST be php
MySQL name MUST be mysql
pod key MUST be pod
pod value MUST be lamp-pod
state MUST be started

Do NOT use:

container_name
pod_name
publish_port
ports
Docker Compose syntax
invented Podman parameter names

PHP and MySQL must be separate containers.podman.podman_container tasks.
Do not use shell/command for container management.
Do not use podman exec.

## PHP Runtime

The PHP container MUST provide PDO MySQL support.

Use exactly:

command:

- sh
- -c
- docker-php-ext-install pdo_mysql && apache2-foreground

Do not use:

- Dockerfile
- Containerfile
- Ansible shell
- Ansible command
- podman exec

## PHP Environment

The PHP container MUST define:

env:
db_host: <Deployment Contract db_host>
db_port: <Deployment Contract db_port>
db_name: <Deployment Contract db_name>
db_user: <Deployment Contract db_user>
db_password: <Deployment Contract db_password>

Use the Deployment Contract values exactly.

- Deployment Contractの値をJinja変数にせず、実値として出力する
- db_portは数値3306として出力する

Do not rename these keys.

## PHP Web Root

The PHP container MUST contain:

volumes:

- /home/vboxuser/containers/html:/var/www/html

## MySQL

The MySQL container MUST contain:

env:

MYSQL_ROOT_PASSWORD: <Deployment Contract db_password>

MYSQL_DATABASE: <Deployment Contract db_name>

MYSQL_DATABASE is mandatory.

The value of MYSQL_DATABASE MUST be exactly the Deployment Contract db_name value.

Do not omit MYSQL_DATABASE.

Do not create the database using Ansible shell, Ansible command, podman exec, or any separate database initialization task.

Do not invent additional database names

## Application File

The playbook MUST contain a separate copy task:

copy:
src: ../src/index.php
dest: /home/vboxuser/containers/html/index.php

Do not add a when condition.

## Minimal Generation

Generate the minimum configuration required by the task and the Deployment Contract.

Do not add unrelated tasks, files, technologies, or configuration.
