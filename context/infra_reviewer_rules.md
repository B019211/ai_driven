# context/infra_reviewer_rules.md

# Infrastructure Review Rules

Review Infrastructure artifacts only.

## Review Objective

Determine whether the generated Infrastructure artifacts are viable for the current pipeline.

Do not review for production perfection.

Reject blocking problems that prevent validation, deployment or browser validation.

## Blocking Problems

Reject only problems that remain after deterministic
Infrastructure Contract validation.

Blocking problems may include:

- unsupported Ansible parameter
- Podman module usage that is incompatible with the project rules
- destructive actions
- infrastructure configuration that clearly prevents deployment
- infrastructure configuration that clearly prevents runtime validation
- PHP runtime configuration that cannot provide required infrastructure functionality
- application logic incorrectly included in Infrastructure `src/index.php`
- security or configuration problems explicitly identified by supplied validation evidence

Do NOT reject the artifact for deterministic structural conditions
that are already validated by the pipeline.

Do NOT independently reject:

- missing `hosts`
- missing `hosts: execution`
- missing `tasks`
- invalid task nesting
- missing Podman pod
- missing PHP container
- missing MySQL container
- missing index.php copy task
- missing inventory entries
- fixed image values
- fixed port values

when those conditions have already been checked by deterministic
validation.

## Context for Review

The following are fixed Infrastructure Contract values already
validated by the pipeline.

Use these values only when evaluating a remaining semantic,
deployment, or runtime issue.

Do not perform independent structural validation of these values.

Pod: lamp-pod
PHP container: php
MySQL container: mysql
PHP image: php:8.2-apache
MySQL image: mysql:8.0
Web root: /var/www/html
Host web path: /home/vboxuser/containers/html
Web publish: 8080:80
Inventory:
[control]
asbsvr

[execution]
rockey8

## Deployment Context

Web: host port 8080 mapped to container port 80
Database: mysql:3306

These values are supplied as deployment context.

Do not independently reject the artifact because of these values
when deterministic validation has already confirmed the contract.

Do not infer application-level configuration requirements from
the Infrastructure Deployment Contract.

## Review Decision

If a blocking problem exists:

"approved": false

and the corresponding risk must have:

"severity": "BLOCKING"

Do not approve a blocking problem as a warning.

If no blocking problem exists:

"approved": true

Warnings are allowed only for non-blocking issues.

## Root Cause

The diagnosis must describe the actual observed problem.

Do not invent a root cause from assumptions.

If the artifact has an invalid Ansible structure, report the structural problem.

Do not report a downstream runtime problem as the root cause when the artifact cannot yet reach runtime validation.

## Repair Compatibility

Review must allow a Repair AI to add required missing structure.

Do not classify the addition of required structural elements as an unnecessary redesign.

For example:

- adding `hosts: execution` to a play that lacks it
- adding `tasks:` around existing tasks
- moving existing task definitions under the required `tasks` list

are valid repairs when the validation evidence requires them.

## Evidence-Based Review

Review the actual generated artifact provided to you.

Do not report a violation unless the violation is directly observable
in the artifact or explicitly supported by the supplied validation evidence.

## Deterministic Validation Boundary

Infrastructure artifact structure is validated separately by the
pipeline's deterministic Infrastructure Contract validation.

The following structural items are deterministic validation
responsibilities and must NOT be independently rejected by the
Reviewer when the supplied artifact facts or parsed artifact show
that they are valid:

- YAML parseability
- play list structure
- hosts
- tasks
- required Podman pod structure
- required PHP container structure
- required MySQL container structure
- required index.php copy task
- required fixed paths, ports, images, container names and values

The Reviewer must use the supplied artifact facts and actual
generated artifact as evidence.

If a required structural element is explicitly present in the
artifact, treat it as present.

For example:

hosts:

- execution

means that the play has a hosts value targeting the execution group.

Do NOT report:

- "missing hosts"
- "missing execution target"
- "missing tasks"
- "task outside tasks"

when the corresponding structure is present in the parsed artifact.

Do not reconstruct or reinterpret valid parsed YAML from its visual
formatting.

Do not infer structural defects from indentation style, key ordering,
line wrapping, or textual appearance when the parsed YAML structure
is valid.

Do not invent variables, Jinja expressions, modules, keys, paths,
ports, containers, or configuration values.

The Reviewer should report only problems that are directly observable
in the artifact or explicitly supported by supplied validation
evidence.

If the deterministic validation evidence and the reviewer's
interpretation disagree, do not invent a blocking structural problem.

Before reporting a missing key, verify that the key is actually absent.
Do not report a structural violation based solely on the textual
appearance of YAML.

When necessary, evaluate the parsed YAML structure rather than
relying on visual indentation or formatting.

Before reporting an invalid Ansible task structure, verify that
the task is not nested under the play's "tasks:" key.

The following structure is valid and must NOT be reported as a violation:

- name: Example
  hosts:
  - execution
    tasks:
  - name: Example task
    ansible.builtin.debug:
    msg: "example"

Do not infer structural problems from formatting, indentation style,
or key ordering when the parsed YAML structure is valid.
