# Infrastructure Rules

Generate and repair Infrastructure artifacts only.

## Required Files

Generate only:

- ansible/playbook.yml
- ansible/inventory.ini
- src/index.php

Paths are relative to SAFE_ROOT.

## Ansible

`ansible/playbook.yml` must be a valid executable Ansible playbook.

Required:

- YAML root is a list
- `hosts: execution`
- `tasks`
- `containers.podman.podman_pod`
- `containers.podman.podman_container`
- Pod state: `started`
- ports only through `podman_pod.publish`
- no container ports
- use `env`, not `environment`
- no unsupported module parameters
- no shell/command Podman management when a Podman module exists

Fixed values:

- pod: `lamp-pod`
- web container: `php`
- database container: `mysql`
- web image: `php:8.2-apache`
- database image: `mysql:8.0`
- web root: `/var/www/html`
- host web path: `/home/vboxuser/containers/html`
- database: `testdb`
- database user: `root`
- database password: `secret`
- database port: `3306`
- publish: `8080:80`

## MySQL

The MySQL container must use:

name: mysql
image: mysql:8.0
state: started

Use:

env:
MYSQL_DATABASE: testdb
MYSQL_ROOT_PASSWORD: secret

Do not redesign the MySQL container.

## index.php Deployment

The playbook must copy:

src/index.php

to:

/home/vboxuser/containers/html/index.php

Use:

copy:
src: "{{ playbook_dir }}/../src/index.php"
dest: /home/vboxuser/containers/html/index.php

Do not specify owner or group.

If mode is specified, use "0644".

ansible/playbook.yml から src/index.php をコピーする場合、Controller上の生成物配置を基準とし、src/index.php を直接指定してはならない。

## Infrastructure PHP

`src/index.php` is only an Infrastructure HTTP validation file.

When the current Infrastructure validation target is HTTP display, use exactly:

<?php
echo "Infrastructure OK";
?>

Do not add application logic or PDO/MySQL connection code.

Infrastructure must provide PHP 8.2, Apache, PDO and `pdo_mysql` for the Application layer.

Infrastructure/Application Boundary

Infrastructure must provide PDO and pdo_mysql as PHP runtime capabilities.

Do not add Application database connection logic to the Infrastructure playbook.

Do not add Deployment Contract database values such as db_host, db_port, db_name, db_user or db_password to the PHP container.

Do not modify or reinterpret Deployment Contract values.

The repair must use a method compatible with the fixed image `php:8.2-apache`.
Do not guess or use a package manager or command that is not available in that image.

## PHP Runtime

Infrastructure must provide:

- PHP 8.2
- Apache
- PDO
- pdo_mysql

The PHP container image must remain:

php:8.2-apache

Do not invent or replace the image with another image name.

The `pdo_mysql` extension may be installed inside the PHP container during container startup.

PHP-image-specific commands such as `docker-php-ext-install`
must not be executed as host-side Ansible tasks.

If required, the PHP container startup command may install
`pdo_mysql` inside the container before starting Apache.

When specifying the startup command for `php:8.2-apache` to install `pdo_mysql` and start Apache, use the following YAML list format:

```yaml
command:
  - sh
  - -c
  - "docker-php-ext-install pdo_mysql && apache2-foreground"
```

Do not use a single string format for the PHP container `command` such as:

```yaml
command: "sh -c 'docker-php-ext-install pdo_mysql && apache2-foreground'"
```

A single string format causes invalid argument splitting inside Podman arguments.

The repair MUST keep the PHP image:
php:8.2-apache

The repair MUST install `pdo_mysql` inside the PHP container
before Apache starts.

The installation method MUST be executed inside the PHP container,
not on the Ansible Controller or Execution Node host.

The repair MUST NOT replace the PHP image with another image.

The repair MUST NOT modify src/index.php to solve the missing driver.

Do not modify src/index.php to solve missing PHP extensions.

## Deployment Contract

Application database connection information comes from the Deployment Contract.

Do not invent, replace or modify its values.

Do not introduce another mechanism for receiving them.

## Deployment Contract Runtime

The Infrastructure task must provide the following Deployment Contract
database values to the PHP runtime as container environment variables:

- db_host
- db_port
- db_name
- db_user
- db_password

The environment variable names must be identical to the Deployment Contract keys.

The Application task may read these values using getenv().

Infrastructure is responsible for providing these environment variables.
Application is responsible only for consuming them.

## Repair

When repairing:

- fix only the reported error
- preserve every valid existing part
- preserve task order unless required
- do not redesign the infrastructure
- do not rewrite validated Podman tasks
- do not change unrelated images, containers, ports, paths, volumes, hosts or environment values
- return the complete corrected file

## Inventory

`ansible/inventory.ini` must remain:

[control]
asbsvr

[execution]
rockey8

Do not use `localhost` or change the host names or structure.

## Minimality

Generate only what the current task and validation require.

Do not invent technologies, files, parameters, libraries, dependencies or infrastructure.
