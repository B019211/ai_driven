# Runtime Architecture

Control Node:

- asbsvr

Execution Node:

- rockey8

Runtime:

- Podman

Pod:

- lamp-pod

Web:

- php:8.2-apache
- port 8080
- docroot /home/vboxuser/containers/html

Database:

- mysql:8.0
- database testdb
