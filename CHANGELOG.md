# CHANGELOG

## Current system

RuleBound is no longer only a constraint fixer. The engine now extracts intent, ranks layouts, proves repairs, prices in integer INR, and emits a single reviewer HTML report.

### RequirementIR
- Typed intermediate representation from the client brief (`rulebound/ir.py`): occupancy, workstation arrangement, storage, collaboration, accessories, material and openness preferences.
- SKU selection consumes IR + catalog only; geometry and pricing still sit behind the trust boundary.

### 7-metric requirement satisfaction
- Occupancy, desks, chairs, storage, collaboration, finish preference, and openness are scored independently, then averaged into an overall percentage shown in Studio and `quality.json`.

### 11-case adversarial suite
- `adversarial_test.py` plus the Counterexample Laboratory (overlap, egress, door swing, wall, desk rear, chair pull-out, unsatisfiable escalation).
- Each case must invalidate the broken candidate, measure millimetres, and either converge Φ → 0 or escalate with trade-offs.

### Dynamic Judge Mode
- `python judge.py` re-runs tests, the official validator, pricing thresholds, arbitration, determinism, DXF, optimization, and semantic audit.
- Writes `EVIDENCE/FINAL_REPORT.html` (open this first), `FINAL_REPORT.json`, `reproducibility.json`, and `JUDGE_MODE.txt`.

### Semantic regression testing & Golden Corpus
- Placement–quote bijection, SKU/finish validity, and Φ = 0 soundness across all five rooms (`rulebound/semantic_audit.py`, 41/41 checks).
- Golden Corpus regression suite (`tests/golden/ROOM-0*_expected.json`): Asserts semantic ground-truth invariants (occupancy, desk count, seat count, status, grand total in INR, zero violations, and SHA-256 byte identity).

### Property-Based Geometry Fuzzing & Metamorphic Suite
- 1,000 deterministic pseudo-random fuzz cases (`tests/test_property_geometry.py`) validating SAT overlap symmetry $A \cap B \equiv B \cap A$, polygon distance metric symmetry $d(A, B) \equiv d(B, A) \ge 0$, crash-freedom under extreme degenerate geometry, containment monotonicity, and solver determinism.
- Formal Metamorphic Testing (`tests/test_metamorphic.py`) proving Translation Invariance (rigid boundary shift preserves relative clearances and $\Phi$), Placement Permutation Invariance (input order preserves output and quote), Deterministic Re-run Invariance, and Equivalent Rotation Encoding ($\theta \equiv \theta \pm 360^\circ$).

### Deterministic evidence
- SHA-256 manifests of the asset pack, engine sources, and OUTPUT artifacts.
- Official `check_determinism.py` plus a reproducibility chain (input → code → pack → execution → output).

### DXF export
- AutoCAD R12 multi-layer `layout.dxf` for every room (walls, doors, egress, furniture, annotations).

### Pricing invariants
- Decimal half-up integer INR; quantity, finish, labour, and freight tables; quote blocked on invariant failure (`RB-PRC-013`).

### Lyapunov proof stream
- Bounded arbitration (`K_max = 50`) with `(candidate, Φ_before, Φ_after, ΔΦ, decision, reason)` traces.

### Decision quality
- Three archetypes ranked on eight weighted dimensions; Candidate B selected on ROOM-01 at 94.1 in the frozen scorecard.
- Counterfactual explainer: **Why not Layout A / C?**
- Layout diff: **What changed?** (coordinates, rule clearances, Φ).

### Studio
- Web CAD workspace, Pareto view, formal invariants certificate, SKU explainability, ROOM-01 hero demo script.

## Earlier notes

### Correctness
- Fixed RB-GEO-004 desk rear clearance
- Fixed RB-GEO-008 chair pull-out clearance
- Added adversarial invariant tests

### Arbitration
- Added strict candidate decision semantics
- Added explicit ΔΦ telemetry
- Added termination assertions

### Pricing
- Added threshold invariant tests
- Added quote reconciliation checks

### Engineering
- Added `judge.py`
- Added evidence reports
- Corrected clean-machine quickstart
