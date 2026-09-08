# Application Goal

Develop the AI CI/CD Dashboard.

# Application Task

Create a PHP web application.

## Requirements

- Generate PHP source code only.
- Target file: `src/index.php`.
- Create a simple PHP page.
- Do not generate infrastructure, Ansible, or Podman configuration.

## Current Stage

DB Connectivity.

Requirements:

- PHP 8.2
- No framework
- MySQL 8.0
- PDO with the MySQL driver
- Use the Deployment Contract for MySQL connection information
- Execute `SELECT 1`
- Display the connection result in the browser
- Display the SQL execution result in the browser
- Display an appropriate error when connection or SQL execution fails

## Completion Criteria

- PHP lint passes.
- Browser displays the application.
- PHP successfully connects to MySQL.
- `SELECT 1` succeeds.
- Browser validation confirms successful MySQL connection and `SELECT 1` execution.

Expected success indicator:

`Connected successfully`

## Deployment Contract Runtime Mechanism

The Deployment Contract database values are provided to the PHP application
through environment variables with the following exact names:

- db_host
- db_port
- db_name
- db_user
- db_password

The application must use getenv() to read these values.

Do not hardcode these values.
