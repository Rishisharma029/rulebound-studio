# ADR-001: Why deterministic verification?

**Status:** Accepted  
**Context:** Commercial fit-outs mix generative layout proposals with life-safety geometry and auditable quotes. A probabilistic model in the authority path cannot be replayed, hashed, or blamed when a corridor fails.

**Decision:** Generative code may propose placements. The moment a candidate crosses the trust boundary, only deterministic geometry, arbitration, and Decimal pricing may accept, repair, or reject it. No LLM participates in verification or money.

**Consequences:** Reviewers can re-run `python runner.py` and compare SHA-256 manifests. Creativity is bounded; correctness is replayable on the released asset pack and Python version recorded in `EVIDENCE/reproducibility.json`.
