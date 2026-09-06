# context/repair_rules.md

## Evidence Priority

Repair decisions MUST prioritize actual validation evidence.

Priority:

1. Runtime / remote validation error
2. Validation stdout/stderr
3. Structured diagnosis
4. Existing artifact
5. Other contextual hints

A diagnosis MUST NOT override explicit validation evidence.

## Minimal Change

Repair only the configuration directly related to the reported error.

Do not modify unrelated valid configuration.

## No-op Repair

A repair that produces identical content is invalid.

The repair process must either:

- resolve the reported problem, or
- explicitly fail rather than silently returning unchanged content.

## YAML

For `ansible/playbook.yml`:

- YAML must remain syntactically valid.
- The root must be a list.
- Each play must contain `hosts` and `tasks`.
- `tasks` must be a list.

## Environment Constraints

- Do not introduce SELinux-related configuration during repair.
- Do not add `:Z` or `:z` to bind mounts.
- Repairs must preserve compatibility with the project's non-SELinux learning environment.# Repair Rules

## Runtime File Visibility

For containerized web applications:

- If validation evidence shows that a required file exists on the host but is missing inside the web container, repair the container-to-host file visibility configuration.
- Do not modify Apache DirectoryIndex configuration unless validation evidence specifically shows a DirectoryIndex configuration problem.
- Do not treat a host-side file copy as proof that the file is available inside the container.
- Preserve the existing host path and container path defined by the project architecture.
  - For ansible/playbook.yml, the following Infrastructure Contract is IMMUTABLE:
    1. PHP container MUST contain:
       volumes:
       - /home/vboxuser/containers/html:/var/www/html

    2. The index.php copy task MUST be:
       copy:
       src: ../src/index.php
       dest: /home/vboxuser/containers/html/index.php

    3. The index.php copy task MUST NOT contain any "when" condition.

    4. MySQL container env MUST remain:
       env:
       MYSQL_ROOT_PASSWORD: secret

    5. Do NOT change the existing pod publish configuration:
       8080:80

    6. Do NOT rename lamp-pod, php, or mysql.

    7. Do NOT change php:8.2-apache or mysql:8.0.

    8. Do NOT replace index.php with index.html.

    9. Do NOT add owner, group, mode, remote_src, validate,
       or other copy parameters to the index.php copy task.

    10. Any repair that violates this contract is INVALID.

- Containerからbind mount対象へのアクセスが可能であること
