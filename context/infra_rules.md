# context/infra_rules.md

# Infrastructure Rules

## Scope

These rules apply to the Infrastructure artifact:

ansible/playbook.yml

The Infrastructure layer is responsible for creating and configuring the LAMP runtime with Ansible and Podman.

The Infrastructure layer must provide the runtime resources required by the Deployment Contract.

Do not add application business logic to the Infrastructure playbook.

---

## Fixed Values

Use these values exactly unless validation evidence explicitly requires a change.

| Item                    | Value                          |
| ----------------------- | ------------------------------ |
| Ansible target group    | execution                      |
| Pod name                | lamp-pod                       |
| PHP container           | php                            |
| MySQL container         | mysql                          |
| PHP image               | php:8.2-apache                 |
| MySQL image             | mysql:8.0                      |
| Host web port           | 8080                           |
| Container web port      | 80                             |
| Host HTML directory     | /home/vboxuser/containers/html |
| Container document root | /var/www/html                  |
| MySQL port              | 3306                           |
| Database                | testdb                         |
| Database user           | root                           |
| Database password       | secret                         |

These values are part of the learning environment contract.

---

## Ansible Playbook Structure

ansible/playbook.yml must be a valid Ansible playbook.

Requirements:

- YAML must be parseable by yaml.safe_load().
- The YAML root must be a list of plays.
- The play must target the execution inventory group.
- Tasks must be under the play's tasks list.
- hosts and tasks must be siblings.
- Do not create a top-level plays key.
- Do not create a top-level playbook key.
- Do not represent each task as a separate play.
- Use Ansible and Podman.

Required structure:

- name: Play name
  hosts:
  - execution
    tasks:
  - name: Task name
    module.name:
    ...

---

## Podman Modules

Use these Ansible modules:

- containers.podman.podman_pod
- containers.podman.podman_container

Do not change to Docker Compose.

Do not invent Podman module parameters.

Do not use shell or command modules for container management.

Do not use podman exec.

---

## Pod Configuration

The web port must be published by the Pod.

The Pod must use:

state: started

The published port must be:

publish:

- "8080:80"

The port publication belongs to containers.podman.podman_pod.

Do not define publish on containers that belong to the shared Pod.

Do not add a second Podman task later to configure the Pod port.

---

## Container Configuration

The PHP and MySQL containers must belong to:

pod: lamp-pod

Both required containers must use:

state: started

PHP must use:

image: php:8.2-apache
name: php

MySQL must use:

image: mysql:8.0
name: mysql

Do not define published host ports on the PHP or MySQL containers.

---

## Environment Variables

Use the Ansible parameter:

env:

Do not use:

environment:

Environment variable values required by the Deployment Contract must come from the Deployment Contract when the value is supplied there.

Do not invent, infer, replace, or modify Deployment Contract values.

---

## MySQL Runtime

The MySQL container must provide the database required by the Deployment Contract.

For the current Learning Phase environment, the required database is:

testdb

The MySQL container must initialize that database.

The MySQL container must preserve:

MYSQL_ROOT_PASSWORD: secret

The database initialization configuration must correspond to the database name defined by the Deployment Contract.

Do not invent additional database names.

Do not invent additional database credentials.

The MySQL service must remain:

image: mysql:8.0
pod: lamp-pod
name: mysql
state: started

---

## PHP Runtime

The PHP container must receive the database values required by the Deployment Contract.

The following environment variable names are mandatory:

- db_host
- db_port
- db_name
- db_user
- db_password

Their values must come from the Deployment Contract provided to the Infrastructure Generate prompt.

The PHP application reads these values using getenv().

The PHP container must provide PDO MySQL support.

The PHP container must remain based on:

php:8.2-apache

For the Learning Phase, PDO MySQL may be enabled by using the container startup command:

command:

- sh
- -c
- docker-php-ext-install pdo_mysql && apache2-foreground

Do not change the PHP image.

Do not introduce a Dockerfile or Containerfile in the Learning Phase.

Do not use Ansible shell or command modules to execute podman exec, container management commands, or runtime installation commands.

The PHP container must remain a member of:

lamp-pod

The PHP web service must continue to listen on container port 80 and be published through the Pod as:

8080:80

---

## PHP Container

The PHP container must serve files from:

/var/www/html

The host directory:

/home/vboxuser/containers/html

must be bind-mounted to:

/var/www/html

The generated application file is:

src/index.php

Its validation content is the responsibility of the application artifact, not the Infrastructure playbook.

---

## Application File Deployment

The generated project layout is:

generated/files/

├── ansible/
│ ├── playbook.yml
│ └── inventory.ini
└── src/
└── index.php

playbook.yml is located under ansible/.

Therefore, when Ansible copy uses src relative to the playbook directory, the source path for index.php is:

../src/index.php

Do not use:

src/index.php

for this layout.

The copy task runs on the execution host, not inside the PHP container.

Therefore the destination must be:

/home/vboxuser/containers/html/index.php

Do not use the container-only path:

/var/www/html/index.php

for the Ansible host-side copy destination.

The resulting file must become available inside the PHP container at:

/var/www/html/index.php

through the bind mount.

The index.php copy task must not use a when condition.

---

## YAML and Jinja Syntax

Jinja expressions used as complete YAML scalar values must be written in a YAML-safe form.

For example:

name: "{{ pod_name }}"

Do not generate malformed YAML by using invalid Jinja expression syntax.

---

## Minimal Change Rule

When repairing an existing playbook:

- Preserve valid existing configuration.
- Change only what is required by the validation evidence.
- Do not redesign the playbook.
- Do not change fixed values without evidence.
- Do not duplicate a configuration to compensate for an invalid configuration.
- If a setting must be moved, replace the invalid location rather than keeping both.
