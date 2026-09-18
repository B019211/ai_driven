# Application Rules

## Application Scope

Generate Application source files only.

Do not generate or modify Infrastructure files, Ansible files, Podman configuration, or Infrastructure runtime configuration.

Generate only files explicitly required by the Application Task.

Do not introduce unrequested frameworks, libraries, services, or dependencies.

The Application runs on the existing PHP 8.2 runtime and available extensions.

Do not use Composer, vendor packages, or third-party libraries unless explicitly required.

## Infrastructure Boundary

Infrastructure must be completed before Application generation starts.

Application uses the existing Infrastructure and must not construct, repair, or redesign it.

Do not modify Infrastructure to solve an Application problem.

If a problem is caused by Infrastructure, report it rather than changing Infrastructure.

## Deployment Contract

The Deployment Contract is the authoritative interface between Infrastructure and Application.

Application must use the Contract values and must not create, modify, replace, or invent Contract values.

Required database values:

- db_host
- db_port
- db_name
- db_user
- db_password

Infrastructure provides these values to the PHP runtime as environment variables with the same names.

Application must obtain them using `getenv()`.

Do not hardcode database connection values.

## Database

When database access is required:

- Use PDO and the available MySQL driver.
- Use the Deployment Contract values.
- Include the Contract-defined database name in the DSN.
- Do not invent or replace database connection values.
- Do not modify Infrastructure to solve database access problems.

When the Application Task requires application database schema or initial data, Application may create and manage application-level tables, indexes, constraints, and initial data.

Application must use the existing Contract-defined database and must not create or replace the database service itself.

## Validation

Application source must have valid PHP syntax and satisfy the Application Task.

Application must run on the existing runtime and reference only existing files and dependencies.

Do not assume missing Contract values or invent alternatives.

## Learning Environment

Do not reject or redesign an Application solely for production-quality concerns that are outside the current Application Task.
