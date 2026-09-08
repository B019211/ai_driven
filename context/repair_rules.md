# context/repair_rules.md

# Repair Rules

## Repair Scope

- Repair only the issue explicitly identified by validation.
- Preserve all existing valid structure and values that are unrelated
  to the reported issue.
- Do not rewrite or restructure the entire file when a local change
  is sufficient.
- Do not remove existing tasks, keys, modules, paths, ports,
  container names, images, or environment values unless the
  validation evidence explicitly identifies them as the cause.
- When adding a missing required task, append or insert only that task.
- When modifying an existing value, change only that value.

## Evidence Priority

Repair decisions MUST prioritize actual validation evidence.

Priority:

1. Runtime / remote validation error
2. Validation stdout/stderr
3. Structured diagnosis
4. Existing artifact
5. Other contextual hints

A diagnosis MUST NOT override explicit validation evidence.

---

## Minimal Change

Repair only the configuration directly related to the reported error.

Do not modify unrelated valid configuration.

Make the minimum change required to resolve the observed error.

Do not redesign the infrastructure.

Do not add unrelated tasks.

Do not introduce files that do not exist.

Modify only the target file.

---

## No-op Repair

A repair that produces identical content is invalid.

The repair process must either:

- resolve the reported problem, or
- explicitly fail rather than silently returning unchanged content.

---

## YAML

For `ansible/playbook.yml`:

- YAML must remain syntactically valid.
- The root must be a list.
- Each play must contain `hosts` and `tasks`.
- `tasks` must be a list.

---

## Infrastructure Preservation

For `ansible/playbook.yml`:

- Preserve the existing architecture.
- Preserve existing image names.
- Preserve existing container names.
- Preserve existing ports.
- Preserve existing volumes unless the observed error requires correcting them.
- Preserve existing environment values.
- Do not introduce Docker Compose.

Do not change infrastructure components that are unrelated to the reported validation error.

---

## Runtime File Visibility

For containerized web applications:

- If validation evidence shows that a required file exists on the host but is missing inside the web container, repair the container-to-host file visibility configuration.
- Do not treat a host-side file copy as proof that the file is available inside the container.
- Preserve the existing host path and container path defined by the project architecture.
- Container access to the bind-mounted host path must remain possible.
- Do not modify Apache DirectoryIndex configuration unless validation evidence specifically shows a DirectoryIndex configuration problem.

---

## Infrastructure Contract

For `ansible/playbook.yml`, the following requirements are IMMUTABLE.

Any repair that violates this contract is INVALID.

### PHP Web Root Volume

The PHP container MUST contain:

    volumes:
      - /home/vboxuser/containers/html:/var/www/html

Do not remove or replace this required volume.

---

### index.php Deployment

The `index.php` copy task MUST be:

    copy:
      src: ../src/index.php
      dest: /home/vboxuser/containers/html/index.php

The `index.php` copy task MUST NOT contain a `when` condition.

Do not add the following parameters to this copy task:

- `owner`
- `group`
- `mode`
- `remote_src`
- `validate`

Do not add unrelated copy parameters.

---

### MySQL Environment

The MySQL container environment MUST remain:

    env:
      MYSQL_ROOT_PASSWORD: secret

Do not change the existing environment value.

---

### Published Port

Do not change the existing pod publish configuration:

    8080:80

---

### Names

Do not rename:

- `lamp-pod`
- `php`
- `mysql`

---

### Images

Do not change:

    php:8.2-apache
    mysql:8.0

---

### Application Entry Point

Do not replace:

    index.php

with:

    index.html

---

## Repair Scope

- Repair only the target file.
- Preserve all valid configuration unrelated to the reported error.
- Do not remove required pods, containers, images, ports, volumes, environment values, or application files.
- Do not introduce Docker Compose.
- Do not introduce unrelated infrastructure components.
- Do not redesign the infrastructure.
- Do not add unrelated tasks.

When validation evidence identifies a specific configuration defect, correct that defect without changing unrelated infrastructure.

---

## Contract Feedback

Deterministic Contract Feedback provided by the pipeline describes the specific Infrastructure Contract violations detected in the current repair attempt.

Treat Contract Feedback as authoritative validation evidence.

Fix every reported Contract violation.

Do not assume that Contract Feedback replaces the rules in this document.

After repair, the resulting file MUST satisfy the complete Infrastructure Contract defined above.

## Repair Evidence Priority

The mandatory repair evidence is the reason the repair is being requested.

When repairing a file, use the following priority:

1. Mandatory repair evidence
2. Runtime validation evidence
3. Validation errors
4. Current target file
5. Deploy evidence
6. Deploy diagnosis

A successful deployment does not mean runtime validation succeeded.

If deployment succeeded but HTTP, Apache, PHP, filesystem, or other runtime validation reports a failure, the runtime validation failure MUST be treated as the active repair problem.

The repairer MUST use the actual validation evidence to determine what must be changed.

Do not ignore runtime validation failures because deployment or deployment diagnosis reports success.

Preserve valid existing configuration.

Do not redesign the infrastructure.

Make the minimum change required to resolve the reported validation failure.
