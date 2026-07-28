# Runtime Architecture

## Inventory

[control]
asbsvr

[execution]
rockey8

Do not place asbsvr under execution.

## Runtime

- Runtime: Podman
- Pod name: lamp-pod
- Required pod state: started

## Podman Rules

- Prefer containers.podman modules over shell.
- Use containers.podman.podman_pod for the pod.
- Use containers.podman.podman_container for containers.
- Publish ports only through podman_pod.publish.
- Do not publish ports from podman_container.
- Use env for container environment variables, not environment.
- Do not use unsupported module parameters.

## Container Expectations

- Web container name: php
- Database container name: mysql
- Web image: php:8.2-apache
- Database image: mysql:8.0
- Web container document root: /var/www/html
- Host path for web files: /home/vboxuser/containers/html
- Database name: testdb
