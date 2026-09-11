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

Use:

- containers.podman.podman_pod
- containers.podman.podman_container

The pod MUST be:

- name: lamp-pod
- ports: 8080:80

The PHP container MUST be a separate podman_container task with:

- image: php:8.2-apache
- pod: lamp-pod
- name: php
- state: started

The MySQL container MUST be a separate podman_container task with:

- image: mysql:8.0
- pod: lamp-pod
- name: mysql
- state: started

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

The database name MUST correspond to the Deployment Contract.

## Application File

The playbook MUST contain a separate copy task:

copy:
src: ../src/index.php
dest: /home/vboxuser/containers/html/index.php

Do not add a when condition.

## Minimal Generation

Generate the minimum configuration required by the task and the Deployment Contract.

Do not add unrelated tasks, files, technologies, or configuration.
