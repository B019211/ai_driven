# AI DevOps Architecture

## Development Environment

- OS: Windows11
- Editor: VSCode
- Connection: Remote SSH

## Control Node

- Hostname: asbsvr
- Role: Ansible Control Node

## Execution Node

- Hostname: rockey8
- Role: Podman Execution Server

## Container Runtime

- Podman

## Pod

- lamp-pod

## Containers

### web container

- Container Name: web
- Image: php:8.2-apache
- Port: 8080
- Document Root: /home/vboxuser/containers/html

### mysql container

- Container Name: mysql
- Image: mysql:8.0
- Database: testdb

## Deployment Flow

1. VSCode edits source
2. AI generates code
3. Ansible deploys files
4. Podman mounts volume
5. PHP container executes application
