# Computer Use development

- Work only in this checkout. Develop and validate sequentially; do not spawn
  agents, create worktrees, or duplicate the application for validation.
- Reuse existing native dependencies and the official Cua release. Keep runtime
  files in the ignored `.build/`, `mdo-home/`, and root executable/config paths.
- Keep Cua unmodified. Do not add workaround prompts, skills, hidden retries,
  window remapping, or custom cancellation behavior for its known issues.
- Use mdo's existing MCP discovery, permissions, media, and lifecycle contracts.
- Commit each small completed milestone after its relevant checks. Never commit
  credentials, runtime Home data, downloaded drivers, or generated binaries.
- Record actual results and limitations; distinguish protocol fixtures from a
  real model completing a desktop task.
