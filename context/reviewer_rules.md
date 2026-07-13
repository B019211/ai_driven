# Review Rules

AI generated artifacts must NEVER:

- overwrite production files directly
- disable security permanently
- expose secrets
- delete data directories
- remove firewall rules
- use force delete unless explicitly approved

Human approval is required before:

- ansible execution
- deploy
- git merge
- container recreation

Reject playbooks that use

shell: podman

when a containers.podman module exists.

Request regeneration instead.

Reject playbooks when:

podman_pod.state is not started

podman_container contains ports

php:8.2-apache is mounted somewhere other than /var/www/html

MySQL container name is not mysql

Reject any playbook that uses
unsupported module parameters.
