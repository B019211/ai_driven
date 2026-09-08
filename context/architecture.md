# Architecture

## Project

This project is an AI-driven CI/CD pipeline for a learning environment.

The pipeline generates, validates, deploys and repairs infrastructure artifacts using AI.

---

## Pipeline Phase

The current phase is:

```text
learning
```

The Infrastructure phase is responsible for preparing the runtime environment required by later phases.

---

## Infrastructure Responsibility

The Infrastructure phase provides:

- Ansible inventory
- Ansible playbook
- Podman pod
- PHP/Apache web container
- MySQL database container
- Web document root
- Infrastructure validation page

Application business logic is outside the Infrastructure phase.

---

## Runtime Architecture

The Infrastructure runtime is structured as:

```text
Ansible
   |
   v
Podman
   |
   +-- lamp-pod
         |
         +-- php
         |     |
         |     +-- Apache / PHP 8.2
         |
         +-- mysql
```

The PHP and MySQL containers share the same Pod.

The application reaches MySQL through the container name:

```text
mysql
```

---

## Web Path

The web request flow is:

```text
Browser
   |
   v
Host :8080
   |
   v
Pod :80
   |
   v
PHP / Apache
   |
   v
/var/www/html
```

The host-side document directory is:

```text
/home/vboxuser/containers/html
```

The container-side document root is:

```text
/var/www/html
```

---

## Database

MySQL runs as a container in the same Pod.

The database is identified inside the Pod by:

```text
mysql
```

The application-side database endpoint is therefore:

```text
mysql:3306
```

Database configuration values are defined by the Infrastructure task and its rules.

---

## Ansible Structure

The generated Ansible playbook represents the Infrastructure runtime described above.

The playbook targets:

```text
execution
```

The playbook uses the Podman Ansible collection to manage:

- the Pod
- the PHP container
- the MySQL container

The Pod is the network boundary for the PHP and MySQL containers.

Published host ports belong to the Pod-level network configuration.

Detailed Infrastructure constraints are defined in:

```text
context/infra_rules.md
```

---

## Artifact Boundaries

Infrastructure artifacts are:

```text
ansible/playbook.yml
ansible/inventory.ini
src/index.php
```

`ansible/playbook.yml` describes runtime infrastructure.

`ansible/inventory.ini` describes the Ansible execution target.

`src/index.php` provides the Infrastructure web validation page.

---

## Deployment Contract

The Infrastructure phase provides the runtime contract required by later phases.

The important runtime endpoints are:

```text
Web:
8080 -> 80

Database:
mysql:3306
```

The Infrastructure phase must provide a reachable web endpoint before later application-level validation can be considered successful.

---

## Validation Boundary

Infrastructure validation verifies that:

1. The Ansible configuration is structurally valid.
2. The Pod can be created and started.
3. Required containers can be created and started.
4. The web port is reachable.
5. Apache/PHP can serve `src/index.php`.
6. The expected Infrastructure validation page can be returned.

Application-level database functionality is validated in a later phase.

---

## Design Principle

Keep Infrastructure configuration deterministic.

Do not introduce configuration that is not required by the Infrastructure task, architecture, or validation evidence.

Infrastructure-specific technical constraints belong in:

```text
context/infra_rules.md
```

Task-specific requirements belong in:

```text
task/infrastructure.md
```
