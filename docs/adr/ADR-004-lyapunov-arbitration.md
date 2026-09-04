# ADR-004: Why bounded Lyapunov arbitration?

**Status:** Accepted  
**Context:** Repairing overlaps by greedy nudges can cycle. Unbounded search is not a product: reviewers need termination, a trace, and an honest unsatisfiable outcome.

**Decision:** Arbitration is a bounded state machine (`K_max = 50`). Each accepted operator must strictly decrease energy  
`Φ(L) = 1000·|V| + Σ penetration + Σ clearance deficit`. Plateau detection prunes low-priority items. Exhaustion emits `unsatisfiable` plus trade-offs; quotes are blocked.

**Consequences:** The proof stream is `(candidate, Φ_before, Φ_after, ΔΦ, decision, reason)`. Monotonicity is an invariant of *accepted* steps in this engine, tested on injected violations—not a theorem over all possible rooms in the universe.
