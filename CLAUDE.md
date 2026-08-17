# Claude entry point

Read `AGENTS.md` first. It is the canonical repository instruction file and
applies equally to Claude, Codex, and human contributors. Do not duplicate or
override its architecture rules here.

Then read the scoped `AGENTS.md` nearest to every file you plan to change and:

1. Use `docs/change-workflow.md` to classify the request and build an impact
   map before editing.
2. Use `docs/ai-prompts.md` for copy-ready feature, fix, and review prompts.
3. Use `docs/feature-playbooks.md` for the relevant change type.
4. Use `docs/testing-strategy.md` to select regression tests.
5. Read related decisions in `docs/adr/` before changing an invariant.
6. Run `make check` before declaring completion.

When asked to implement a feature or fix, continue autonomously when the
requested behavior is clear. Ask for clarification only when different choices
would materially change accounting, stored data, or user-visible behavior.

Never expose secrets, rewrite an applied migration, physically delete output
history, bypass repository boundaries, or hand-edit generated field metadata.
