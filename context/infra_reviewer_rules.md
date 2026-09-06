# Infrastructure Review Rules

Review Infrastructure artifacts only.

## Review Objective

Determine whether the generated Infrastructure artifacts are viable for the current pipeline.

Do not review for production perfection.

Reject blocking problems that prevent validation, deployment or browser validation.

## Blocking Problems

The following are blocking:

- invalid YAML
- YAML root is not a list of Ansible plays
- missing `hosts`
- missing `hosts: execution`
- missing `tasks`
- `tasks` is not a list
- Podman task exists outside a play
- Podman task exists outside the `tasks` list
- missing Podman pod
- missing PHP container
- missing MySQL container
- invalid fixed image
- unsupported Ansible parameter
- Pod state is not `started`
- container ports are used instead of `podman_pod.publish`
- `environment` is used instead of `env`
- Podman is managed by shell/command when a Podman module exists
- required `index.php` deployment is missing
- PHP runtime cannot provide `pdo_mysql`
- Infrastructure `src/index.php` contains application DB logic
- required inventory entries are missing

## Required Values

Pod:

- `lamp-pod`

PHP container:

- `php`

MySQL container:

- `mysql`

PHP image:

- `php:8.2-apache`

MySQL image:

- `mysql:8.0`

Web root:

- `/var/www/html`

Host web path:

- `/home/vboxuser/containers/html`

Web publish:

- `8080:80`

Inventory:

```ini
[control]
asbsvr

[execution]
rockey8
```

## Deployment Contract

Infrastructure must provide:

- `db_host`
- `db_port`
- `db_name`
- `db_user`
- `db_password`

to the PHP runtime using environment variables with exactly those names.

The values must match the current Deployment Contract.

## Review Decision

If a blocking problem exists:

```json
"approved": false
```

and the corresponding risk must have:

```json
"severity": "BLOCKING"
```

Do not approve a blocking problem as a warning.

If no blocking problem exists:

```json
"approved": true
```

Warnings are allowed only for non-blocking issues.

## Root Cause

The diagnosis must describe the actual observed problem.

Do not invent a root cause from assumptions.

If the artifact has an invalid Ansible structure, report the structural problem.

Do not report a downstream runtime problem as the root cause when the artifact cannot yet reach runtime validation.

## Repair Compatibility

Review must allow a Repair AI to add required missing structure.

Do not classify the addition of required structural elements as an unnecessary redesign.

For example:

- adding `hosts: execution` to a play that lacks it
- adding `tasks:` around existing tasks
- moving existing task definitions under the required `tasks` list

are valid repairs when the validation evidence requires them.
