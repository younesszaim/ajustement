# Migration rules

Migrations are ordered, forward-only, and may already exist in shared
databases.

- Never edit an applied migration to change behavior; add the next numbered
  migration.
- Make rerunnable setup safe where practical (`IF NOT EXISTS`), while keeping
  data transformations explicit.
- Preserve append-only output protections and audit history.
- Add indexes only for demonstrated access paths and explain them in comments.
- Never put credentials, environment-specific hosts, or passwords in SQL.
- Keep `vertica_sim` output and `adjustment_meta` audit concerns isolated.
- Update schema installer expectations and add an adapter/integration test for
  any schema contract change.
- Provide rollback guidance in documentation when SQL cannot be safely undone.
