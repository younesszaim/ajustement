# Enrichment library rules

This package contains production-shaped DataFrame calculations.

- Functions receive and return DataFrames without changing row count or order.
- Rule functions derive values from the input frame and context only.
- Parameter functions receive mapping DataFrames from the orchestrator; they do
  not read files, S3, environment variables, or databases.
- Register functions explicitly in `registry.py`; no dynamic import by name.
- Field names come from `app.data_dictionary.FIELDS`.
- Declare complete inputs, outputs, calculation type, and mapping dependency.
- Preserve deterministic results and do not mutate caller-owned frames.
- Raise explicit validation errors for missing, ambiguous, or invalid matches.
- Tests cover exact matches, wildcard priority, ambiguity, nulls, unchanged
  cardinality, and execution metadata.

When adding a stage, update the registry, `STAGE_DEPENDENCIES`, mapping
configuration/manifest when applicable, semantic dictionary, and tests.
