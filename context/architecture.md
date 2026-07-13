# Runtime Architecture

Inventory Rules

[control]
asbsvr

[execution]
rockey8

Never put asbsvr into execution.

Runtime:

- Podman

Pod:

- lamp-pod

Podman Rules
Always use
containers.podman.podman_pod
instead of shell.

State must be started.
Podman Rules

Always use containers.podman modules when available.
Never use shell for Podman management.
Pod must be managed by:
containers.podman.podman_pod
Required state:
started
Port publishing:
publish:

- "8080:80"
  Do not publish ports from podman_container.
  Container names:
  php
  mysql

Web

Image:
php:8.2-apache

Host path:
/home/vboxuser/containers/html

Container path:
/var/www/html

Database

- mysql:8.0
- database testdb
