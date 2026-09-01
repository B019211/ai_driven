# Application Review Rules

Review only application artifacts.

## Reject

Reject when:

- PHP syntax is clearly invalid
- the application cannot execute under the existing PHP runtime
- required application functionality is missing
- unsupported PHP extensions or frameworks are introduced
- infrastructure files are generated
- Ansible files are generated
- Podman configuration is generated
- existing infrastructure is unnecessarily modified

Temporary local-learning compromises are allowed when they do not block the pipeline.

## MySQL

When MySQL connectivity is required:

- use the existing MySQL service name
- use the existing database name
- use PDO with the available MySQL driver
- do not redesign the MySQL container
- do not modify infrastructure configuration

## Scope

Do not review Ansible or Podman implementation details as application errors.

Reject application code for infrastructure issues only when the application explicitly viola
