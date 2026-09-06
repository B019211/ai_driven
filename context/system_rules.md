# context/system_rules.md

# System Rules

- Generate only requested files.
- Do not generate destructive commands.
- Do not invent technologies, files, parameters, or configuration.
- Preserve valid existing configuration.
- Modify only the requested scope.
- Use UTF-8.
- Structured output must contain no explanatory prose.

## Security / Environment Constraints

- SELinux is not used in this learning environment.
- Do not introduce, configure, enable, or require SELinux for generated infrastructure.
- Do not add SELinux-related mount options such as `:Z` or `:z`.
- Do not add SELinux policy, labeling, or security-context configuration.
- Bind mounts must work without SELinux-specific configuration.
