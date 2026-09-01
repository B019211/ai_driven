# Application Rules

## Application Scope

- Generate application source files only.
- Do not generate or modify infrastructure, Ansible, or Podman configuration.
- Generate only files explicitly requested by the application task.
- Do not redesign infrastructure or introduce unrequested frameworks, services, or dependencies.

## Deployment Contract

The Application task receives a Deployment Contract from the Infrastructure task.

The Deployment Contract is the authoritative source for infrastructure-provided connection information.

Before generating application code, read the Deployment Contract and use its values consistently.

Do not guess, infer, replace, invent, or modify Contract values.

For database access, the following values MUST come from the Deployment Contract:

- db_host
- db_port
- db_name
- db_user
- db_password

Do not guess, replace, or invent these values.

The Application task must not modify the Deployment Contract.

The Application task must not invent a runtime mechanism for receiving
Deployment Contract values.

Do not assume database connection values are available through environment
variables unless the task explicitly defines environment variables as the
runtime mechanism.

If the runtime mechanism is not defined, do not introduce getenv(), default
values, placeholders, or alternative connection settings.

## Database Access

- Use PHP 8.2 compatible syntax.
- Use PDO with the MySQL driver.
- Database connection values MUST come from the Deployment Contract.
- The runtime mechanism for providing Contract values MUST be explicitly defined.
- Do not invent environment variable names or other runtime mechanisms.
- Construct the PDO DSN from db_host, db_port, and db_name.
- Use db_user and db_password for authentication.

## Runtime Mechanism

The Infrastructure task provides the Deployment Contract values to the PHP runtime through environment variables.

The environment variable names are exactly:

- db_host
- db_port
- db_name
- db_user
- db_password

Application code MUST read these values using getenv().

Do not hardcode database connection values.
Do not introduce alternative runtime mechanisms.

## Validation

- Generated PHP must pass PHP syntax validation.
- Application behavior must be validated through the existing deployment environment.
- Database connectivity must use the Deployment Contract values.
- If required Contract values are missing, do not invent alternatives.
