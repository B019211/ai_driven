app_rules.md

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

Do not introduce unrequested frameworks, services, libraries, or dependencies.

The application must run using the existing PHP runtime and its available extensions.

For the current Application Task, use only PHP built-in functionality and the PDO MySQL driver already provided by the existing PHP runtime.

Do not introduce Composer, a vendor directory, an autoloader, or third-party libraries.

Do not add require or require_once statements for dependency files that are not part of the generated application.

Do not reference vendor/autoload.php.

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

Application code must use getenv() to read them.

Do not hardcode connection values.

## Database Access

When database access is required:

- use PHP 8.2 compatible syntax

- use PDO

- use the MySQL PDO driver

- construct the DSN from db_host, db_port, and db_name

- include charset in the DSN

- authenticate using db_user and db_password

The database name MUST NOT be omitted from the DSN.

The generated application must not invent database host, database name, user, password, or port values.

Do not modify Infrastructure to solve an Application problem.

## Validation

Generated PHP must:

- pass PHP syntax validation

- execute in the existing Infrastructure runtime

- use the Deployment Contract

- satisfy the current Application Task

- reference only files and dependencies that exist in the application environment

If required Contract values are missing, stop.

Do not invent alternatives.

## Database Connectivity Validation

When the current Application Task requires database connectivity, the application must verify connectivity using:

SELECT 1

The result comparison must account for PDO's returned scalar value potentially being represented as a string.

Do not use strict integer comparison against an uncast PDO result.
