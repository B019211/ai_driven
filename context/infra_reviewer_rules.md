# Infrastructure Review Rules

Review Infrastructure artifacts only.

Reject when any of these is true:

- invalid Ansible play structure
- missing `hosts: execution`
- missing tasks
- missing Podman pod
- missing PHP container
- missing MySQL container
- invalid fixed image
- unsupported Ansible/Podman parameter
- Pod state is not `started`
- container ports are used instead of `podman_pod.publish`
- `environment` is used instead of `env`
- Podman is managed by shell/command when a module exists
- required `index.php` copy is missing
- PHP runtime cannot provide `pdo_mysql`
- Infrastructure `src/index.php` contains application DB logic

Required:

- pod: `lamp-pod`
- PHP container: `php`
- MySQL container: `mysql`
- web image: `php:8.2-apache`
- MySQL image: `mysql:8.0`
- web root: `/var/www/html`
- copy `src/index.php` to `/home/vboxuser/containers/html/index.php`

Inventory must contain:

[control]
asbsvr

[execution]
rockey8

Do not use `localhost`.

Blocking errors must set:

- `approved`: false
- severity: `BLOCKING`

Do not approve blocking errors with warnings.

Approve when the artifact is viable and no blocking error exists.
Do not reject merely for production-quality improvements.
