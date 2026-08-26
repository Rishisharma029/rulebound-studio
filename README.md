# RuleBound: The Sealed Build Challenge

[![Deterministic](https://img.shields.io/badge/Determinism-Byte--Identical-success.svg)](#determinism)
[![Constraint Validation](https://img.shields.io/badge/Constraints-100%25%20Verified-brightgreen.svg)](#spatial-constraints)
[![Tests](https://img.shields.io/badge/Test%20Suite-11%20Passed-blue.svg)](#testing)
[![Bonus Track](https://img.shields.io/badge/AutoCAD%20DXF-Supported-orange.svg)](#bonus-tracks)
[![Bonus Track](https://img.shields.io/badge/Azure%20Entra%20ID-Integrated-blueviolet.svg)](#bonus-tracks)

**RuleBound** is an enterprise-grade commercial layout synthesizer, spatial constraint verifier, bounded arbitration state machine, and byte-identical pricing engine designed for **Northwind Furnishings**.

---

## Quickstart

### 1. One-Command Pipeline Execution
Generate `layout.json`, `quote.json`, and `layout.dxf` across all rooms in an input pack:

```bash
python main.py --input RuleBound_Round1_Release/data --output OUTPUT
# or:
python runner.py --input RuleBound_Round1_Release/data --output OUTPUT
```

### 2. Validate Output Compliance
Run the official output validator:

```bash
python RuleBound_Round1_Release/tools/validate_output.py OUTPUT
```
```text
OUTPUT VALID
```

### 3. Verify Determinism
Verify byte-identical outputs across repeated runs:

```bash
python RuleBound_Round1_Release/tools/check_determinism.py --command 'python runner.py --input \"{input}\" --output \"{output}\"' --input RuleBound_Round1_Release/data --work-dir .determinism-check
```
```text
DETERMINISTIC: 15 files are byte-identical
```

### 4. Run Test Suite
```bash
python -m pytest
```

---

## Core System Architecture

| Component | Module | Description |
|---|---|---|
| **Data Models & Loader** | `rulebound/models.py`, `rulebound/loader.py` | Strongly typed dataclasses for rooms, catalog items, finishes, rules, placements, and quotes. |
| **Spatial Geometry** | `rulebound/geometry.py` | Separating Axis Theorem (SAT), 2D polygon containment, wall distances, door swing arcs, and egress capsules. |
| **Constraint Engine** | `rulebound/constraints.py` | Deterministic verification of RB-GEO-001 through RB-GEO-008 with structured violation metrics. |
| **Arbitration Engine** | `rulebound/arbitration.py` | Bounded repair state machine with monotonic Lyapunov energy minimization and escalation handling. |
| **Pricing Engine** | `rulebound/pricing.py` | Exact integer INR arithmetic, basis point uplifts, quantity discounts, labor bands, and freight tiers. |
| **Generative Planner** | `rulebound/generator.py` | Brief-aware spatial layout synthesizer producing ergonomic, collision-free furniture pods. |
| **DXF CAD Engine** | `rulebound/dxf.py` | 2D AutoCAD-compatible DXF layout exporter with distinct CAD layers and DXF boundary importer. |
| **Enterprise REST API** | `rulebound/api.py` | FastAPI microservice secured by Microsoft Entra ID (Azure AD) JWT Bearer authentication. |

---

## Key Deliverables

- [`ARCHITECTURE.md`](ARCHITECTURE.md): System design document featuring the required **Arbitration** section (seam contract, irreversible handoff, Lyapunov termination proof, unsatisfiable escalation).
- [`DETERMINISM.md`](DETERMINISM.md): Formal determinism statement and hash verification tables.
- [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md): Complete script for the 5-minute video demonstration showcasing deliberate violation injection and autonomous repair.
- [`OUTPUT/`](OUTPUT/): Committed, validated, byte-identical outputs for all five released benchmark rooms (`ROOM-01` through `ROOM-05`).
- [`azure-deploy.bicep`](azure-deploy.bicep) & [`Dockerfile`](Dockerfile): Complete Azure Cloud deployment scaffolding.
