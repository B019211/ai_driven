# context/infra_rules.md

# Infrastructure Rules

## Scope

These rules apply to the infrastructure artifact:

- `ansible/playbook.yml`

The infrastructure layer is responsible for creating and configuring the LAMP containers with Ansible and Podman.

Do not add application logic to the infrastructure playbook.

---

## Fixed Values

Use these values exactly unless validation evidence explicitly requires a change.

| Item                    | Value                            |
| ----------------------- | -------------------------------- |
| Ansible target group    | `execution`                      |
| Pod name                | `lamp-pod`                       |
| PHP container           | `php`                            |
| MySQL container         | `mysql`                          |
| PHP image               | `php:8.2-apache`                 |
| MySQL image             | `mysql:8.0`                      |
| Host web port           | `8080`                           |
| Container web port      | `80`                             |
| Host HTML directory     | `/home/vboxuser/containers/html` |
| Container document root | `/var/www/html`                  |
| MySQL port              | `3306`                           |
| Database                | `testdb`                         |
| Database user           | `root`                           |
| Database password       | `secret`                         |

These values are part of the learning environment contract.

---

## Ansible Playbook Structure

`ansible/playbook.yml` must be a valid Ansible playbook.

Requirements:

- YAML must be parseable by `yaml.safe_load()`.
- The YAML root must be a list of plays.
- The play must target the `execution` inventory group.
- Tasks must be under the play's `tasks` list.
- Do not create a top-level `plays` key.
- Do not create a top-level `playbook` key.
- Do not represent each task as a separate play.
- Ansible + Podmanを使用する

---

## Podman Modules

Use these Ansible modules:

- `containers.podman.podman_pod`

- `containers.podman.podman_container`

- Docker Composeへ変更しない

Do not invent Podman module parameters.

Do not use `shell` or `command` to perform container management.

---

## Pod Configuration

The web port must be published by the Pod.

The Pod must use:

```
state: started
```

The published port must be:

```
publish:
  - "8080:80"
```

The port publication belongs to `containers.podman.podman_pod`.

Do not define `publish` on containers that belong to the shared Pod.

Do not add a second Podman task later to configure the Pod port.

---

## Container Configuration

The PHP and MySQL containers must belong to:

```
pod: lamp-pod
```

Use:

```
state: started
```

for the required running containers.

Do not define published host ports on the PHP or MySQL containers.

---

## Environment Variables

Use the Ansible parameter:

```
env:
```

Do not use:

```
environment:
```

For MySQL, preserve the required environment contract:

```
MYSQL_ROOT_PASSWORD=secret
```

Do not invent additional database credentials.

---

## PHP Container

Use:

```
php:8.2-apache
```

The PHP container must serve files from:

```
/var/www/html
```

The host directory:

```
/home/vboxuser/containers/html
```

is bind-mounted to:

```
/var/www/html
```

The generated application file is:

```
src/index.php
```

Its validation content is the responsibility of the application artifact, not the infrastructure playbook.

---

## Application File Deployment

The generated project layout is:

```
generated/files/
├── ansible/
│   ├── playbook.yml
│   └── inventory.ini
└── src/
    └── index.php
```

`playbook.yml` is located under `ansible/`.

Therefore, when Ansible `copy` uses `src` relative to the playbook directory, the source path for `index.php` is:

```
../src/index.php
```

Do not use:

```
src/index.php
```

for this layout.

The `copy` task runs on the execution host, not inside the PHP container.

Therefore the destination must be the host directory that is bind-mounted into the container:

```
{{ html_mount }}/index.php
```

Do not use the container-only path:

```
{{ document_root }}/index.php
```

for the Ansible host-side `copy` destination.

The resulting file must become available inside the PHP container at:

```
/var/www/html/index.php
```

through the bind mount.

---

## YAML and Jinja Syntax

Jinja expressions used as complete YAML scalar values must be written in a YAML-safe form.

For example:

```
name: "{{ pod_name }}"
```

Do not generate unquoted Jinja expressions such as:

```
name: { { pod_name } }
```

when that produces invalid YAML.

---

## Minimal Change Rule

When repairing an existing playbook:

- Preserve valid existing configuration.
- Change only what is required by the validation evidence.
- Do not redesign the playbook.
- Do not change fixed values without evidence.
- Do not duplicate a configuration to compensate for an invalid configuration.
- If a setting must be moved, replace the invalid location rather than keeping both.
