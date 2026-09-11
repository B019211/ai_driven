app_reviewer_rules.md

# Application Review Rules

Review Application artifacts only.

## Reject

Reject when:

- PHP syntax is invalid

- required application functionality is missing

- the application cannot execute under the existing PHP runtime

- unsupported PHP extensions or frameworks are introduced

- unrequested dependencies are introduced

- the application references files or dependencies that do not exist in the application environment

- infrastructure files are generated

- Ansible files are generated

- Podman configuration is generated

- the application modifies Infrastructure unnecessarily

- the Deployment Contract is modified or replaced

- database connection values are hardcoded

- the application invents an alternative runtime mechanism

- required Contract values are ignored

## MySQL

When MySQL connectivity is required:

- use the existing MySQL service name

- use the existing database name

- use PDO with the available MySQL driver

- use the Deployment Contract

- do not redesign the MySQL container

- do not modify Infrastructure configuration

## Scope

Do not review Ansible or Podman implementation details as Application errors.

Reject application code for an infrastructure issue only when the application explicitly violates an Application rule.

## Learning Environment

Temporary local-learning compromises are allowed when they do not block the pipeline.

Do not reject solely for production-quality improvements outside the current task.

## Review Decision

Reject only blocking problems.

Blocking problems must set:

"approved": false

and use:

"severity": "BLOCKING"

Warnings are for non-blocking issues.
