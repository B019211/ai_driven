# System Rules

## Development Rules

- Podman only
- Ansible deployment only
- Never use Docker
- Never generate destructive commands.
- Never generate markdown
- Never generate explanations
- UTF-8 only
- Do not generate files other than those requested by the task.

必要最低限の内容でよい。

途中省略は禁止。
Empty content is prohibited.

Ansible Playbookでは
hosts: execution を使用すること。
hosts: all は使用しないこと。

Podman Podでは
-pはpod createでのみ指定すること。
podman runでは-pを指定しないこと。

# Ansible Rules

Use Ansible modules whenever possible.

Do not execute Podman using shell commands unless absolutely necessary.

Use the containers.podman collection.

Preferred modules:

- containers.podman.podman_pod
- containers.podman.podman_container

Generated playbooks should be idempotent.

Avoid shell:
shell: podman run ...

Avoid shell:
shell: podman pod create ...

Prefer:

containers.podman.podman_pod

containers.podman.podman_container

# Preferred Ansible Modules

Package
ansible.builtin.dnf

File
ansible.builtin.copy
ansible.builtin.template

Service
ansible.builtin.systemd

Podman
containers.podman.podman_pod
containers.podman.podman_container

SELinux
community.general.sefcontext

Firewall
ansible.posix.firewalld

Never use shell when one of the above modules exists.

containers.podman.podman_podでは
timeoutパラメータは禁止。

containers.podman collection 1.19.1で
サポートされていないパラメータは使用しない。

Validation結果に
Unsupported parameters
が出たら、
そのパラメータは削除して再生成すること。
