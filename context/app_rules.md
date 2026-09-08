# Application Rules

## Application Scope

Generate application source files only.

Do not generate or modify:

- Infrastructure files
- Ansible files
- Podman configuration
- infrastructure runtime configuration

Generate only files explicitly requested by the Application Task.

Do not redesign Infrastructure.

Do not introduce unrequested frameworks, services or dependencies.

## Infrastructure Boundary

Infrastructure must already be completed before Application generation starts.

Application generation must not start when Infrastructure completion is false.

The Application receives the Deployment Contract from the completed Infrastructure phase.

The Application must not create or modify the Deployment Contract.

## Deployment Contract

The Deployment Contract is authoritative.

Required values:

- db_host
- db_port
- db_name
- db_user
- db_password

Do not:

- guess values
- infer values
- replace values
- invent values
- modify values
- introduce an alternative runtime mechanism

## Runtime Mechanism

Infrastructure provides the Deployment Contract database values to the PHP runtime through environment variables.

The environment variable names are exactly:

- db_host
- db_port
- db_name
- db_user
- db_password

Application code must use `getenv()` to read them.

Do not hardcode connection values.

## Database Access

When database access is required:

- use PHP 8.2 compatible syntax
- use PDO
- use the MySQL PDO driver
- construct the DSN from `db_host`, `db_port`, and `db_name`
- authenticate using `db_user` and `db_password`

Do not modify Infrastructure to solve an Application problem.

## Validation

Generated PHP must:

- pass PHP syntax validation
- execute in the existing Infrastructure runtime
- use the Deployment Contract
- satisfy the current Application Task

If required Contract values are missing, stop.

Do not invent alternatives.
