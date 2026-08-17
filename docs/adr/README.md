# Architecture decision records

Use ADRs for decisions that change an invariant, dependency direction, storage
contract, calculation orchestration, or cross-cutting frontend pattern. Small
implementation details do not need an ADR.

Files use `NNNN-short-title.md`. Copy `0000-template.md`, assign the next
number, and mark the status Proposed, Accepted, Superseded, or Deprecated.

An agent must read relevant accepted ADRs before proposing an incompatible
change. If a new requirement supersedes a decision, keep the old ADR and link
both records rather than rewriting history.
