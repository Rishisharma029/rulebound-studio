# 📜 RuleBound Studio Engineering Changelog

## [v1.0.0] - Round 3 Final Submission (2026-09-02)

### ✨ Core Innovations & Major Upgrades
- **Intermediate Requirement Graph (`RequirementIR`)**: Decoupled natural language parsing from catalog SKU matching and spatial layout solving.
- **Requirement Satisfaction Scoring**: Implemented 7-metric brief-to-layout satisfaction scoring engine with live UI scorecard.
- **Lyapunov Arbitration Proof System**: Upgraded arbitration from heuristic repair to formal descent proof stream emitting explicit `(candidate_id, action, phi_before, phi_after, delta_phi, decision, decision_reason)` records.
- **Data-Driven Verifier Architecture**: 100% data-driven binding to `rules.yaml` with zero hardcoded rule thresholds.
- **True 2D Geometric Exclusion Zones**: Implemented genuine polygon zones for desk rear clearance (`RB-GEO-004`) and task chair dynamic pull-out (`RB-GEO-008`).
- **Formally Audited Pricing Pipeline**: Integrated 6-point accounting invariant verification with automated quote blocking (`RB-PRC-013`).
- **Comprehensive Adversarial Benchmark Matrix**: Added 29 automated edge-case and boundary tests with machine-readable reporting in `EVIDENCE/`.
- **One-Command Reviewer Judge Mode (`judge.py`)**: End-to-end verification and evidence generation tool with clear ASCII audit verdict.

---

## [v0.5.0] - Round 2 Studio & CAD Engine (2026-09-01)
- **Interactive Web Studio CAD UI**: Real-time canvas rendering with dynamic layer controls and hover telemetry HUD.
- **AutoCAD Release 12 DXF Engine (+5 Bonus)**: Multi-layer CAD blueprint exporter (`layout.dxf`).
- **Line Item Price Trace Modal**: Interactive mathematical derivation viewer for financial accounting.

---

## [v0.1.0] - Initial Prototype (2026-08-30)
- Initial SAT 2D collision detection and basic pricing calculator.
