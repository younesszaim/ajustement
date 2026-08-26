# Streamlit application test guide

The root and `streamlit_app/AGENTS.md` instructions apply.

## Testing approach

- Tests must run without Supabase or Vertica unless explicitly marked as an
  integration test.
- Use small output/operation fakes to exercise `AdjustmentService` behavior.
- Inject a fake calculator and capture its row, semantic-column mapping,
  overrides, callback, and delay arguments.
- Test API routes by replacing `runtime()` dependencies; do not monkeypatch
  database drivers when a repository fake is sufficient.
- Test ordered calculation names, earliest affected stage, override precedence,
  row-count protection, progress callbacks, and zero-delay default.
- Test background jobs for success and exception states. Avoid timing-sensitive
  assertions; wait on a short deadline and assert terminal snapshots.
- Compare business values and lineage fields explicitly. Avoid snapshots of
  whole rows when a focused assertion explains the invariant better.

## Minimum regression matrix

A replacement change normally covers:

- context match and mismatch;
- inactive/missing source;
- original, negative reversal, adjusted values and IDs;
- invalid controlled field/value and no-op change;
- calculation start order and returned steps;
- first commit, idempotent retry and retry-key conflict;
- changed amount/field/reason/context/source after failure or commit;
- complete-intention validation before COMMITTED return and reconciliation;
- output failure and metadata-confirmation failure.

A revert change normally covers:

- missing, non-REPLACE, failed, already reverted, and inactive targets;
- `-adjusted + restored original` values and lineage;
- retry-key conflict and idempotent recovery;
- atomic metadata relationship between revert and target.

A cancellation change normally covers:

- preview/build of one negative reversal and no replacement;
- one generated output ID, inactive source and idempotent exact retry;
- changed-key intention conflicts and output/metadata partial failure;
- revert through one restored active row linked to the cancellation.

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest streamlit_app/tests -q
```

Do not add shared-database credentials or tests that mutate production-like
Supabase data to this unit suite.
