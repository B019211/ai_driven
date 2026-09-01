# Runtime Architecture

Inventory:

- control: asbsvr
- execution: rockey8

Runtime:

- Podman
- pod: lamp-pod
- pod state: started

Containers:

- web: php
- web image: php:8.2-apache
- database: mysql
- database image: mysql:8.0

Web:

- document root: /var/www/html
- host path: /home/vboxuser/containers/html
- PDO MySQL is required

Database:

- name: mysql
- image: mysql:8.0
- database: testdb

Podman:

- prefer containers.podman modules
- use podman_pod for the pod
- use podman_container for containers
- publish ports through podman_pod
- use env, not environment
- never invent module parameters
