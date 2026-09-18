# Application Review Rules

## Review Scope

Review Application artifacts only.

Review against the Application Task, Application Rules, and Deployment Contract.

Do not treat Infrastructure, Ansible, Podman, container, or deployment implementation details as Application defects unless the Application explicitly violates an Application rule.

## Reject

Reject only blocking Application problems.

Reject when:

- PHP syntax is invalid.
- Required Application functionality is missing.
- Application cannot run on the existing PHP runtime.
- Unsupported or unrequested dependencies are introduced.
- Nonexistent files or dependencies are referenced.
- Infrastructure or Ansible files are generated or modified.
- Deployment Contract is modified or replaced.
- Required Contract values are ignored.
- Database connection values are hardcoded.
- An alternative runtime configuration mechanism replaces the Contract.
- Application attempts to replace the Contract-defined database or database service.

## Deployment Contract

When database access is required, verify that Application uses:

- db_host
- db_port
- db_name
- db_user
- db_password

through the Contract-defined runtime environment.

Do not require Application to create or modify the Contract.

## Database

When database functionality is required:

- Use the existing MySQL service.
- Use the Contract-defined database.
- Use PDO with the available MySQL driver.
- Do not redesign Infrastructure.

When the Application Task requires application schema or initial data, creating application-level tables, indexes, constraints, or initial data is valid Application behavior.

Do not reject application schema creation merely because Infrastructure does not create those tables.

## Infrastructure Boundary

Do not reject Application for an Infrastructure problem that is outside Application responsibility.

Do not fabricate downstream, container, networking, deployment, or runtime defects from Application source.

## Learning Environment

Do not reject solely for production-quality concerns outside the current Application Task.

## Review Decision

Blocking problem:

- `approved = false`
- severity = `BLOCKING`

Non-blocking issue:

- `approved = true`
- report as warning

Reject only concrete, evidence-based blocking problems.
