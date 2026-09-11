#context/architecture.md

# Architecture

## Project

This project is an AI-driven CI/CD pipeline for a learning environment.

The pipeline generates, validates, deploys and repairs infrastructure artifacts using AI.

---

## Pipeline Phase

The current phase is:

learning

The Infrastructure phase is responsible for preparing the runtime environment required by later phases.

---

## Infrastructure Responsibility

The Infrastructure phase provides the runtime environment required by later phases.

Its responsibilities include:

- Ansible inventory
- Ansible playbook
- Podman pod
- PHP/Apache web container
- MySQL database container
- Web document root
- Required database initialization
- Infrastructure validation page
- Infrastructure validation

The Infrastructure phase must make the database required by the Deployment Contract available to the application.

Application business logic and application data initialization are outside the Infrastructure phase unless explicitly required by the Deployment Contract.

---

## Runtime Architecture

The Infrastructure runtime is structured as:

Ansible
|
v
Podman
|
+-- lamp-pod
|
+-- php
| |
| +-- Apache / PHP 8.2
|
+-- mysql

The PHP and MySQL containers share the same Pod.

The application reaches MySQL through the container name:

mysql

The database service is therefore reachable from the PHP container at:

mysql:3306

---

## Web Path

The web request flow is:

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

The host-side document directory is:

/home/vboxuser/containers/html

The container-side document root is:

/var/www/html

The host-side directory is mounted into the PHP container so that application files become available under the container document root.

---

## Database

MySQL runs as a container in the same Pod as PHP.

The database service is identified inside the Pod by:

mysql

The application-side database endpoint is:

mysql:3306

The database required by the application is defined by the Deployment Contract.

The Infrastructure phase is responsible for ensuring that the contracted database exists and is available to the application.

Database-specific implementation details are defined in:

context/infra_rules.md

---

## Ansible Structure

The generated Ansible playbook represents the Infrastructure runtime described above.

The playbook targets:

execution

The playbook uses the Podman Ansible collection to manage:

- the Pod
- the PHP container
- the MySQL container

The Pod is the network boundary for the PHP and MySQL containers.

Published host ports belong to the Pod-level network configuration.

Detailed Infrastructure constraints are defined in:

context/infra_rules.md

---

## Artifact Boundaries

Infrastructure artifacts are:

ansible/playbook.yml
ansible/inventory.ini
src/index.php

ansible/playbook.yml describes runtime infrastructure.

ansible/inventory.ini describes the Ansible execution target.

src/index.php provides the Infrastructure web validation page.

The Infrastructure phase must not add application business logic to these artifacts.

---

## Deployment Contract

The Infrastructure phase provides the runtime contract required by later phases.

The important runtime endpoints are:

Web:
8080 -> 80

Database:
mysql:3306

The Deployment Contract also defines the database configuration required by the application.

The Infrastructure phase must provide the contracted runtime resources before later application-level validation can be considered successful.

---

## Validation Boundary

Infrastructure validation verifies that:

1. The Ansible configuration is structurally valid.
2. The Pod can be created and started.
3. Required containers can be created and started.
4. The web port is reachable.
5. Apache/PHP can serve src/index.php.
6. The expected Infrastructure validation page can be returned.
7. The database required by the Deployment Contract is available.

Application-level business logic and application-specific database behavior are validated in a later phase.

---

## Design Principle

Keep Infrastructure configuration deterministic.

Do not introduce configuration that is not required by the Infrastructure task, architecture, Deployment Contract, or validation evidence.

Infrastructure responsibilities are defined here.

Infrastructure-specific technical constraints are defined in:

context/infra_rules.md

Task-specific requirements belong to:

task/infrastructure.md

Repair-specific behavior is defined in:

context/repair_rules.md
