# Infrastructure Task

## Goal

Build the Infrastructure layer for the learning-phase AI-driven CI/CD pipeline.

The result must provide a runnable Podman-based LAMP environment that can be validated remotely and through a browser.

---

## Required Artifacts

Generate exactly these required artifacts:

```text
ansible/playbook.yml
ansible/inventory.ini
src/index.php
```

---

## Ansible Playbook

Create:

```text
ansible/playbook.yml
```

The playbook must target:

```text
execution
```

It must create and start:

- Pod: `lamp-pod`
- PHP container: `php`
- MySQL container: `mysql`

Use the Podman Ansible modules.

The web service must be exposed through:

```text
8080:80
```

The web port must be published at the Pod level.

The PHP container must use:

```text
php:8.2-apache
```

The MySQL container must use:

```text
mysql:8.0
```

The PHP container must mount:

```text
/home/vboxuser/containers/html:/var/www/html
```

The generated `src/index.php` must be available from the web document root.

---

## MySQL Configuration

The Infrastructure runtime must provide the database contract required by the later Application phase.

Use:

```text
Host: mysql
Port: 3306
Database: testdb
User: root
Password: secret
```

---

## PHP Runtime

The PHP runtime must be based on:

```text
php:8.2-apache
```

PDO MySQL support (`pdo_mysql`) must be available.

The Infrastructure phase must not implement database application logic.

---

## Inventory

Create:

```text
ansible/inventory.ini
```

It must define the execution host:

```text
[execution]
rockey8
```

The control node may be defined as:

```text
[control]
asbsvr
```

---

## Infrastructure Validation Page

Create:

```text
src/index.php
```

The page is used only to verify that the Infrastructure web service is working.

A successful response must display:

```text
Infrastructure OK
```

Do not implement database connectivity or other application business logic in this file.

---

## Validation Requirements

The generated Infrastructure must pass:

1. File existence validation.
2. YAML syntax validation.
3. Ansible playbook structure validation.
4. Inventory validation.
5. Remote Ansible validation.
6. Podman deployment.
7. Pod/container runtime validation.
8. Browser HTTP validation.
9. PHP runtime validation.

---

## Completion Criteria

The Infrastructure task is complete when:

- all required artifacts exist;
- `ansible/playbook.yml` is valid YAML;
- the playbook has the required Ansible structure;
- the required Pod and containers can be created;
- the web port is reachable at host port `8080`;
- Apache/PHP can serve `src/index.php`;
- the browser can receive the Infrastructure validation page;
- the response contains:

```text
Infrastructure OK
```

---

## Phase Boundary

This task creates the runtime foundation for the Application phase.

Do not add Application-phase functionality to the Infrastructure artifacts.

Application database connectivity and business logic are outside this task.
