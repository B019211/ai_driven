# Repair Rules

## Repair Purpose

Repair the target file only when validation evidence identifies a concrete problem.

The purpose of repair is to correct the identified problem while preserving all valid existing configuration.

The repairer must not redesign the infrastructure.

The repairer must not improve, optimize, simplify, or restructure configuration unless validation evidence requires that change.

## Repair Evidence Priority

Repair decisions must prioritize actual evidence in the following order:

1. Mandatory repair evidence
2. Runtime or remote validation error
3. Validation stdout or stderr
4. Contract Feedback
5. Structured diagnosis
6. Current target artifact
7. Deploy evidence
8. Deploy diagnosis
9. Other contextual hints

A diagnosis must not override explicit validation evidence.

A successful deployment does not mean runtime validation succeeded.

If deployment succeeds but HTTP, Apache, PHP, filesystem, database, or other runtime validation reports a failure, the runtime validation failure is the active repair problem.

The repairer must use the actual evidence to determine what must be changed.

## Minimal Change

Repair only the configuration directly related to the reported problem.

Preserve all valid configuration that is unrelated to the reported problem.

Make the minimum change required to resolve the observed problem.

When modifying an existing value, change only that value.

When correcting an invalid parameter, replace the invalid parameter with the required parameter.

Do not keep both the invalid parameter and the replacement parameter.

When adding a missing required task, add only that task.

Do not remove existing tasks, keys, modules, paths, ports, container names, images, or environment values unless the validation evidence explicitly identifies them as the cause.

Do not add unrelated tasks.

Do not introduce unrelated infrastructure components.

Do not introduce files that do not already belong to the target architecture.

Modify only the target file.

## No-op Repair

A repair that produces identical content is invalid when the reported problem remains unresolved.

The repair process must either resolve the reported problem or explicitly fail.

Do not silently return unchanged content when the identified problem still exists.

## YAML Structure

For ansible/playbook.yml:

- The YAML must remain syntactically valid.
- The root must be a list of plays.
- Each play must contain hosts.
- Each play must contain tasks.
- The tasks value must be a list.
- Hosts and tasks must be siblings within the play.
- Do not create a top-level playbook object.
- Do not make each task a separate play.

## Infrastructure Preservation

Preserve the existing infrastructure architecture unless validation evidence explicitly requires a change.

Preserve:

- Podman architecture
- pod name
- container names
- image names
- published ports
- bind mount paths
- database connection values
- required environment values
- application deployment paths
- required infrastructure tasks

Do not introduce:

- Docker Compose
- Dockerfile
- Containerfile
- unrelated infrastructure components
- alternative container orchestration
- unnecessary health checks
- unnecessary readiness checks
- unnecessary retry logic
- diagnostic tasks
- workaround tasks

## Runtime Recovery

When runtime validation reports that the existing Infrastructure Pod or its required containers are stopped, runtime recovery is a valid Infrastructure repair target.

If the current playbook contains `state: started` but re-running the playbook leaves the existing Pod or its containers stopped, the repairer must not assume that the existing `state: started` configuration is sufficient.

The repairer may modify or add the minimum Ansible configuration required to make re-running the playbook restore the existing Infrastructure to the required running state.

Runtime recovery must operate on the existing:

- lamp-pod
- php
- mysql

Do not create duplicate resources.

Do not move runtime recovery into the Python pipeline.

Do not use manual recovery as the final solution.

Do not use Ansible block for the required infrastructure tasks.

Required infrastructure tasks must remain direct sibling entries under the play tasks list.

The PHP container task and the index.php copy task must be separate tasks.

The PHP container task must contain only the container deployment action and its required parameters.

The index.php deployment must be a separate task using the copy action.

If the PHP container task and the index.php copy task are combined into one task, separate them into two sibling tasks.

If the PHP container task and the index.php copy task are placed inside a block, move them to separate sibling tasks under tasks.

Do not use block as a replacement for separate sibling tasks.

## Runtime File Visibility

For containerized web applications, a host-side file is not proof that the file is available inside the web container.

If validation evidence shows that a required file exists on the host but is missing inside the web container, inspect and repair the container-to-host file visibility configuration.

Preserve the project-defined host path and container path.

The PHP container must retain access to the required bind-mounted host directory.

Do not modify Apache DirectoryIndex configuration unless validation evidence specifically identifies DirectoryIndex configuration as the cause.

## Infrastructure Contract

The following infrastructure values are fixed.

Any repair that changes these values without explicit validation evidence is invalid.

### Pod

The pod must use the containers.podman.podman_pod module.

The pod must use:

- name: lamp-pod
- state: started
- publish: 8080:80

The parameter for the pod name is name.

Do not use:

- pod_name
- publish_port
- ports
- container/pod_name

Do not replace name with another parameter.

Do not create a second pod.

### PHP Container

The PHP container must use the containers.podman.podman_container module.

The PHP container must use:

- name: php
- image: php:8.2-apache
- pod: lamp-pod
- state: started

The pod parameter must be the scalar value lamp-pod.

Do not use container_name.

Do not use a mapping object for the pod parameter.

Do not use pod with a nested name value.

Do not publish a host port from the PHP container.

The host port is published by the pod.

### MySQL Container

The MySQL container must use the containers.podman.podman_container module.

The MySQL container must use:

- name: mysql
- image: mysql:8.0
- pod: lamp-pod
- state: started

The pod parameter must be the scalar value lamp-pod.

Do not use container_name.

Do not use a mapping object for the pod parameter.

Do not use pod with a nested name value.

Do not publish a host port from the MySQL container.

The MySQL container must provide the database required by the Deployment Contract.

### Fixed Names

Do not rename:

- lamp-pod
- php
- mysql

### Fixed Images

Do not change:

- php:8.2-apache
- mysql:8.0

### Fixed Published Port

The pod must publish:

- 8080:80

Do not move host port publication from the pod to a container.

### Fixed PHP Volume

The PHP container must contain the following bind mount:

- /home/vboxuser/containers/html:/var/www/html

The PHP container must contain the following bind mount:

- /home/vboxuser/containers/html:/var/www/html

Do not remove this volume.

Do not replace the host path.

Do not replace the container path.

When runtime evidence identifies an SELinux bind-mount labeling problem, the same bind mount may use the :Z suffix:

- /home/vboxuser/containers/html:/var/www/html:Z

In that case, :Z is a labeling option on the existing required bind mount, not a replacement of the host path or container path.

## PHP Runtime

The PHP container must provide PDO MySQL support.

For the Learning Phase, the PHP container must use the following startup command when enabling PDO MySQL:

- sh
- -c
- docker-php-ext-install pdo_mysql && apache2-foreground

The startup command must be configured as a parameter of the containers.podman.podman_container action.

Preserve:

- image: php:8.2-apache
- name: php
- pod: lamp-pod

Do not replace the PHP image.

Do not introduce Dockerfile-based solutions.

Do not introduce Containerfile-based solutions.

Do not use Ansible shell for container management.

Do not use Ansible command for container management.

Do not use podman exec.

## PHP Environment

The PHP container must define an env mapping for the database connection values required by the application.

The required environment variable names are:

- db_host
- db_port
- db_name
- db_user
- db_password

The values must come from the corresponding Deployment Contract fields.

Use the Deployment Contract values exactly.

Do not rename these variables.

Do not convert them to uppercase names.

Do not replace them with alternative names such as:

- DB_HOST
- DB_PORT
- DB_NAME
- DB_USER
- DB_PASSWORD

Do not invent alternative database connection values.

Do not move the PHP database connection values into the MySQL container environment.

The PHP environment and MySQL environment have separate responsibilities.

## MySQL Environment

The MySQL container must preserve the required root password:

- MYSQL_ROOT_PASSWORD: secret

The MySQL container must initialize the database required by the Deployment Contract.

The required database is:

- MYSQL_DATABASE: testdb

Do not change the required database name.

Do not create additional databases.

Do not create additional credentials.

Do not change the required root password.

## Application Deployment

The playbook must contain the required index.php copy task.

The copy task must use:

- src: ../src/index.php
- dest: /home/vboxuser/containers/html/index.php

The source path must not be changed.

The destination path must not be changed.

The index.php copy task must not contain a when condition.

Do not add these parameters to the index.php copy task:

- owner
- group
- mode
- remote_src
- validate

Do not add unrelated copy parameters.

The application entry point must remain index.php.

Do not replace index.php with index.html.

## Contract Feedback

Contract Feedback is deterministic validation evidence generated by the pipeline.

Treat Contract Feedback as authoritative evidence of Infrastructure Contract violations.

Fix every reported Contract violation.

Do not assume that Contract Feedback replaces the rules in this document.

Contract Feedback identifies the current violation.

This document defines the complete Infrastructure Contract that must be satisfied after repair.

After repair, the resulting ansible/playbook.yml must satisfy both:

- every reported Contract Feedback violation
- the complete Infrastructure Contract in this document

## Repair Restrictions

The repairer must not add configuration merely because it appears useful.

Do not add:

- wait_for tasks
- register parameters
- when conditions
- health check tasks
- readiness checks
- retry tasks
- diagnostic tasks
- workaround tasks

An additional deployment task is permitted only when runtime validation explicitly identifies a stopped existing Pod or container as the reported failure and the task directly restores that existing resource to the required running state.

Such a task must not create a second Pod or container.

unless the mandatory repair evidence explicitly requires that specific configuration.

Do not solve a parameter error by adding another task.

Do not solve a parameter error by adding a workaround.

Correct the invalid parameter directly.

For example, if validation identifies that a Podman pod task requires the name parameter, change the pod name configuration to use the required name parameter.

Do not introduce a different parameter as a workaround.

If validation identifies an invalid container name parameter, replace it with the required name parameter.

Do not keep both parameters.

If validation identifies an invalid pod configuration, correct the existing pod configuration.

Do not add a second pod.

## Required Infrastructure Task Structure

The required infrastructure tasks must remain separate sibling tasks under the play tasks list.

The infrastructure must contain separate tasks for:

- pod creation
- PHP container creation
- MySQL container creation
- index.php deployment

The PHP container task must use the containers.podman.podman_container action.

The MySQL container task must use the containers.podman.podman_container action.

The index.php deployment must use the copy action.

Do not combine these responsibilities into one task.

Do not place them inside block.

Do not create additional tasks to compensate for an incorrectly configured existing task.

HTTP 403 with Apache unable to read .htaccess may indicate an SELinux bind-mount labeling issue. If runtime evidence supports this diagnosis, change the existing PHP volume from /home/vboxuser/containers/html:/var/www/html to /home/vboxuser/containers/html:/var/www/html:Z.

## Repair Decision Rules

When validation identifies a specific defect:

- Identify the exact configuration causing the defect.
- Change only that configuration.
- Preserve all unrelated valid configuration.
- Re-check the complete Infrastructure Contract after the change.
- Ensure the repair did not introduce a new invalid parameter.
- Ensure the repair did not introduce an unrelated task.
- Ensure the repaired YAML remains syntactically valid.

When a configuration is already valid:

- Preserve it.
- Do not rewrite it.
- Do not replace it with an alternative implementation.
- Do not add a second implementation.

## Final Repair Validation

Before returning the repaired file, verify all of the following:

- The YAML is syntactically valid.
- The root is a list of plays.
- Each play contains hosts and tasks.
- The Pod uses the containers.podman.podman_pod module.
- The Pod uses name: lamp-pod.
- The Pod uses state: started.
- The Pod uses publish for 8080:80.
- The PHP container uses the containers.podman.podman_container module.
- The PHP container uses name: php.
- The PHP container uses image: php:8.2-apache.
- The PHP container uses pod: lamp-pod as a scalar value.
- The PHP container uses state: started.
- The MySQL container uses name: mysql.
- The MySQL container uses image: mysql:8.0.
- The MySQL container uses pod: lamp-pod as a scalar value.
- The MySQL container uses state: started.
- The PHP container retains the required web root volume.
- The PHP container retains the required database environment variables.
- The MySQL container retains MYSQL_ROOT_PASSWORD: secret.
- The MySQL container contains MYSQL_DATABASE: testdb.
- The index.php copy task uses the required source path.
- The index.php copy task uses the required destination path.
- The index.php copy task has no when condition.
- No invalid Podman parameter has been introduced.
- No unrelated task has been introduced.
- No wait_for task has been introduced.
- No unnecessary register parameter has been introduced.
- No unnecessary when condition has been introduced.
- No block has been introduced for the required infrastructure tasks.
- No Docker Compose, Dockerfile, or Containerfile solution has been introduced.
- No required fixed infrastructure value has been changed.

## Final Output

Return the complete repaired ansible/playbook.yml file.

Do not return only the changed section.

Do not return an explanation instead of the repaired file.

Do not return multiple alternative implementations.

The returned file must be the single repaired version that satisfies the reported validation evidence and the complete Infrastructure Contract.

## CRITICAL DIRECT REPAIR INSTRUCTION

The current browser validation failure is HTTP 403 Forbidden.

You MUST change the PHP container volume mount.

FROM:
/home/vboxuser/containers/html:/var/www/html

TO:
/home/vboxuser/containers/html:/var/www/html:Z

The ":Z" suffix is REQUIRED.

The old volume:
/home/vboxuser/containers/html:/var/www/html

MUST NOT appear in the repaired playbook.

The PHP container MUST contain exactly:

volumes:

/home/vboxuser/containers/html:/var/www/html

Also preserve these existing requirements:

pod name: lamp-pod
pod publish: 8080:80
PHP image: php:8.2-apache
MySQL image: mysql:8.0
MySQL database: testdb
index.php MUST be copied to /home/vboxuser/containers/html/index.php
Do not use publish_port_map
Do not redesign unrelated infrastructure

This is a DIRECT REPAIR instruction, not a request for diagnosis.

Follow the required volume change exactly.

Return the complete corrected ansible/playbook.yml as valid Ansible YAML.
