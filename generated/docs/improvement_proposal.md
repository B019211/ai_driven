# Improvement

## Title: Implement Git-based Source Code Management (SCM)
## Reason:
The current deployment flow mentions "VSCode edits source" and "AI generates code" but lacks a mechanism for version control. Introducing Git is fundamental for any development and operations workflow. It provides:
*   **Version Control:** Track changes, revert to previous versions, and understand the history of the codebase.
*   **Collaboration:** Enable multiple developers (and the AI) to work on the same codebase concurrently without conflicts, facilitating a shared source of truth.
*   **Auditing and Traceability:** Maintain a clear record of who made what changes and why, improving accountability.
*   **Foundation for Automation:** Essential prerequisite for any continuous integration/continuous deployment (CI/CD) pipeline, even a simplified one triggered by Ansible.
*   **Reliable Deployment:** Ensures Ansible always deploys a known, versioned state of the application.
## Priority: Critical
## Implementation:
1.  **Initialize Git Repository:** Create a Git repository (e.g., on `asbsvr` itself, or a dedicated Git service like Gitea/GitHub/GitLab).
2.  **Developer Workflow Integration:**
    *   Developers push their edited source code from VSCode (via Remote SSH to `asbsvr` and then to the Git repo).
    *   The AI generates code and commits it to this repository.
3.  **Ansible Pull Strategy:** Modify Ansible playbooks to clone or pull the latest version of the application code from this Git repository onto `rockey8` before deploying it to the web container's document root. This ensures that the deployed application consistently reflects the latest, version-controlled state.

## Title: Declarative Podman Deployment with Systemd Units and Persistent Storage
## Reason:
The current "Podman mounts volume" and "PHP container executes application" steps are vague and suggest manual or ad-hoc container management. This approach lacks idempotency, reliability, and proper data persistence for the database.
*   **Idempotency:** Ansible can ensure the desired state of the `lamp-pod` and its containers is always met, creating, updating, or restarting only when necessary, preventing unintended side effects.
*   **Reliability & Auto-Restart:** Systemd units provide robust process management. They ensure the pod and its containers automatically start on host boot and restart gracefully upon failure, improving application uptime.
*   **Data Persistence for MySQL:** Crucial to prevent data loss. A named Podman volume guarantees that the `testdb` data persists across container restarts, upgrades, or even re-creations.
*   **Clear Definition:** Systemd unit files offer a declarative way to define the `lamp-pod` structure, container configurations, port mappings, and volume mounts, making the infrastructure state transparent and auditable.
*   **Simplified Management:** Standard `systemctl` commands can be used on `rockey8` to manage the application lifecycle, providing familiar tooling for administrators.
## Priority: Critical
## Implementation:
1.  **Define Systemd Unit Files:** Create systemd unit files (`.service`) for the `lamp-pod` and its containers (`web`, `mysql`) on `rockey8`. These files will specify:
    *   The `php:8.2-apache` image for the `web` container, mapping container port 80 to a host port (e.g., 80 or 8080).
    *   A bind mount for the web document root (`/home/vboxuser/containers/html`) from the host.
    *   The `mysql:8.0` image for the `mysql` container, initializing `testdb`.
    *   A named Podman volume (e.g., `mysql_data`) mounted to `/var/lib/mysql` inside the `mysql` container for data persistence.
    *   Environment variables for MySQL credentials (to be supplied securely via Ansible Vault).
2.  **Ansible Automation:**
    *   Ansible tasks will `template` these systemd unit files to `/etc/systemd/system/` on `rockey8`.
    *   Ansible will ensure the `mysql_data` Podman volume exists (e.g., using `podman volume create` or `community.general.podman_volume`).
    *   Ansible will then use the `systemd` module to `daemon-reload`, `enable`, and `start` (or `restart`) the relevant Podman systemd services, ensuring the pod and containers are running as desired.

## Title: Implement Secrets Management with Ansible Vault
## Reason:
Hardcoding sensitive information like database credentials directly in playbooks or container definitions is a significant security risk.
*   **Security:** Protects sensitive data (e.g., MySQL root password, application database credentials) by encrypting it at rest within your Ansible project.
*   **Compliance:** Adheres to industry best practices for handling credentials and other confidential information.
*   **Centralized Management:** Provides a secure and consistent method for managing all secrets required by the application and infrastructure.
## Priority: High
## Implementation:
1.  **Create Vault File:** Use `ansible-vault create` to create an encrypted file (e.g., `group_vars/rockey8/secrets.yml`) containing necessary credentials (e.g., `mysql_root_password`, `mysql_user`, `mysql_password`).
2.  **Vault Password Management:** Establish a secure and documented method for managing the Ansible Vault password (e.g., an external password file, environment variable, or secure prompt).
3.  **Ansible Playbook Integration:** Update Ansible playbooks to reference variables from the encrypted `secrets.yml` file.
4.  **Inject Secrets into Containers:** Pass these decrypted secrets as environment variables to the `mysql` container (e.g., `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`) via the systemd unit file definitions, and potentially to the `web` container for PHP database connections.

## Title: Expose Web Service via Standard Port with Host Firewall Configuration
## Reason:
The `web` container exposes on `8080`. While this is functional, exposing applications on standard ports (80 for HTTP, 443 for HTTPS) is a best practice for accessibility and user experience. Also, proper firewall configuration is crucial for security.
*   **Accessibility:** Allows users to access the application without needing to specify a non-standard port (`:8080`) in the URL.
*   **Security:** Explicitly configure the host firewall on `rockey8` to only allow necessary incoming traffic to the application's exposed port.
*   **Standardization:** Aligns with common web server configurations.
## Priority: Medium
## Implementation:
1.  **Podman Port Mapping:** Ensure the `web` container within `lamp-pod` is mapped from its internal port 80 to a desired host port on `rockey8` (e.g., `80` or `8080` if 80 is unavailable/unwanted for direct mapping).
2.  **Ansible Firewall Configuration:** Use Ansible's `firewalld` (or `ufw`) module to open the chosen host port (e.g., 80 or 8080) on `rockey8`, allowing incoming traffic to reach the Podman container.
3.  **Optional: Reverse Proxy:** For production-grade setups, consider deploying a lightweight reverse proxy (like Nginx or Caddy) directly on `rockey8` (outside the `lamp-pod`) to handle incoming HTTP/HTTPS traffic on ports 80/443 and forward it to the `web` container on its designated host port (e.g., 8080). This also enables easier SSL termination. Given the simplicity rules, direct port mapping is the primary recommendation.

---

# Ansible Changes

*   **Source Code Retrieval:** Add tasks to clone/pull the Git repository onto `rockey8` using the `git` module.
*   **Podman Volume Management:** Add tasks to ensure Podman named volumes (e.g., `mysql_data`) exist on `rockey8` using the `community.general.podman_volume` module or `podman volume create` via the `command` module.
*   **Systemd Unit Deployment:** Add tasks using the `template` module to generate and deploy `lamp-pod.service`, `web.service`, and `mysql.service` (or a single consolidated pod service) files to `/etc/systemd/system/` on `rockey8`. These templates will incorporate dynamic values, including secrets from Ansible Vault.
*   **Systemd Service Management:** Add tasks using the `systemd` module to `daemon-reload`, `enable`, and `start`/`restart` the newly deployed Podman systemd services.
*   **Secrets Integration:** Update playbooks to use `ansible-vault` encrypted files. Ensure variables from the vault are correctly passed as environment variables (`Environment=...`) within the Podman systemd unit files.
*   **Firewall Configuration:** Add tasks using the `firewalld` (or `community.general.ufw`) module to manage firewall rules on `rockey8`, opening the port(s) required for web access.
*   **PHP Code Deployment:** Modify existing file deployment tasks to deploy PHP code from the Git-cloned directory on `rockey8` to the web container's document root (`/home/vboxuser/containers/html`).

# Directory Changes

*   **Ansible Control Node (`asbsvr`):**
    *   `project-root/`:
        *   `playbook.yml`: Main Ansible playbook orchestrating deployment.
        *   `inventory.ini`: Ansible inventory file defining `asbsvr` and `rockey8`.
        *   `group_vars/rockey8/secrets.yml`: **New.** Encrypted Ansible Vault file containing sensitive variables for `rockey8` (e.g., MySQL passwords).
        *   `roles/`:
            *   `lamp_app/`: (Or similarly named role for the application)
                *   `tasks/main.yml`: Tasks for Git pull, volume creation, systemd unit deployment, firewall setup, service management.
                *   `templates/`:
                    *   `lamp-pod.service.j2`: **New.** Jinja2 template for the Podman `lamp-pod` systemd unit file. This will define the `web` and `mysql` containers within the pod, their images, ports, volumes, and environment variables.
        *   `src/`: **New.** This will be the root of your Git repository, containing the `html/` directory with PHP source code. (Ansible will clone this to `rockey8`).

*   **Execution Node (`rockey8`):**
    *   `/home/vboxuser/containers/html/`: This directory will be the mount point for the web container's document root. It will be populated by Ansible cloning the Git repository.
    *   `/var/lib/podman/volumes/mysql_data/_data/`: **New.** This will be the persistent storage location for your MySQL database data (assuming a named volume called `mysql_data`).
    *   `/etc/systemd/system/`: **New/Updated.** Location for the deployed Podman systemd unit files (e.g., `lamp-pod.service`).

# Risks

*   **Increased Complexity:** Introducing Git, Ansible Vault, and systemd units adds initial setup and operational complexity compared to a purely manual approach. This requires a learning curve for involved personnel.
*   **Security Management:** Improper handling or exposure of the Ansible Vault password could compromise all encrypted secrets. Secure management of the vault password is paramount.
*   **Configuration Drift:** If manual changes are made directly on `rockey8` (e.g., to Podman containers or systemd units) outside of the Ansible deployment process, they might be overwritten or cause conflicts during subsequent Ansible runs.
*   **AI Integration:** Ensuring the AI-generated code consistently adheres to the specified PHP/PDO rules and integrates seamlessly with the Git repository structure and the application's expected environment.
*   **Resource Consumption:** Running services in containers incurs some overhead. While Podman is lightweight, the total resource usage on `rockey8` should be monitored.
*   **Network Exposure:** Incorrectly configured firewall rules could inadvertently expose services to the internet that should remain internal, or conversely, block legitimate traffic.
*   **Downtime during Deployment:** Without advanced CI/CD techniques (e.g., blue/green, rolling updates), redeployments might incur brief service downtime. This is mitigated by Ansible's idempotent nature, but application restarts are still a factor.