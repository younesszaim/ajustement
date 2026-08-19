# Simple application migration guide

The root and `streamlit_app/AGENTS.md` instructions apply.

## Durable model

The simplified application intentionally owns one PostgreSQL metadata table:
`adjustment_simple.adjustment_operations`. Do not introduce another table for
transient UI state, calculation progress, mappings, or copied business rows.
The output table remains the business journal in Vertica or `vertica_sim`.

## Migration rules

- Migrations are numbered, ordered, forward-only, and safe to apply once.
- Never rewrite a migration already applied to Supabase or another environment.
- Add a new numbered file for a column, constraint, index, or data repair.
- Use `IF NOT EXISTS` only where it makes replay operationally safe without
  hiding an incompatible existing definition.
- Preserve the unique idempotency-key constraint.
- Preserve JSON payload/output IDs needed for recovery and review.
- Revert relationships are audit links, not cascading deletion relationships.
- Do not add credentials, project URLs, or environment-specific owners.
- Document application order in `streamlit_app/README.md` and architecture docs.

Before handoff, explain whether the migration was only authored or actually
applied, which environment was touched, and how to verify or roll forward.
