# Demo Video Walkthrough Script (5-Minute Maximum)

This script provides the complete walkthrough narrative for the official Round 1 demo video.

---

## Video Outline & Timestamps

| Timestamp | Segment | Description |
|---|---|---|
| **0:00 – 0:45** | **Introduction & Architecture** | Explain the challenge problem, Northwind Furnishings domain, and system seam between proposal and deterministic engine. |
| **0:45 – 1:30** | **End-to-End One-Command Run** | Execute `python runner.py --input RuleBound_Round1_Release/data --output OUTPUT` and run `validate_output.py`. |
| **1:30 – 3:15** | **Deliberate Violation & Autonomous Repair** | Inject deliberate spatial violations (egress blocking + overlapping workstations) and demonstrate the Arbitration Engine repairing them. |
| **3:15 – 4:00** | **Deterministic Line-Traceable Pricing** | Inspect `OUTPUT/ROOM-01/quote.json` and reconcile with `REF-QUOTE-01` down to the exact rupee. |
| **4:00 – 4:45** | **Bonus Features: DXF CAD & Azure Entra ID** | Showcase exported `.dxf` CAD drawings and FastAPI REST service with Microsoft Entra ID authentication. |
| **4:45 – 5:00** | **Determinism Statement & Conclusion** | Run `check_determinism.py` and present final conclusions. |

---

## Detailed Step-by-Step Walkthrough

### 1. Introduction (0:00 - 0:45)
- **Visual**: Show `ARCHITECTURE.md` diagram and codebase directory structure.
- **Voiceover**: 
  > *"Welcome to RuleBound: The Sealed Build Challenge. In commercial office fit-outs, salespeople receive complex briefs and floor plans that take days to convert into reliable quotes. RuleBound solves this by decoupling generative layout synthesis from a pure deterministic verification, arbitration, and pricing engine."*

---

### 2. End-to-End Execution (0:45 - 1:30)
- **Action**: Open terminal and execute:
  ```bash
  python runner.py --input RuleBound_Round1_Release/data --output OUTPUT
  python RuleBound_Round1_Release/tools/validate_output.py OUTPUT
  ```
- **Voiceover**: 
  > *"With a single documented command, the system loads all room specs, resolves 120 SKUs, evaluates 14 geometric and pricing rules, and produces verified `layout.json`, `quote.json`, and CAD `layout.dxf` files across all five rooms. The output validator confirms 100% compliance."*

---

### 3. Deliberate Violation & Autonomous Arbitration Repair (1:30 - 3:15)
- **Action**: Run the dedicated demonstration test:
  ```bash
  python -m pytest tests/test_arbitration.py -v
  ```
- **Code Walkthrough**:
  1. Open `tests/test_arbitration.py` and show the injected invalid layout:
     - Two overlapping desks placed at `(50mm, 50mm)` violating wall offset (`RB-GEO-005`) and non-overlap (`RB-GEO-006`).
  2. Show the initial verifier output: `violations = 2`, `energy_score = 2200.0`.
  3. Show the Arbitration Engine activating:
     - Calculates Separating Axis Theorem (SAT) penetration depth.
     - Displaces placement along outward normal vector.
     - Decreases Lyapunov energy metric monotonically $\Phi(L_0) \to \Phi(L_1) \to 0$.
     - Resolves to `status: "valid"`.
- **Voiceover**: 
  > *"Here we inject deliberate spatial violations: two workstations overlapping by 400mm against a wall. The deterministic verifier catches both RB-GEO-005 and RB-GEO-006. The Arbitration Engine executes micro-nudges along the SAT separation normal, driving the Lyapunov energy metric to zero in bounded passes without probabilistic retries."*

---

### 4. Deterministic Pricing Reconciliation (3:15 - 4:00)
- **Action**: Open `OUTPUT/ROOM-01/quote.json` and compare side-by-side with `worked_examples/REF-QUOTE-01.md`:
  - Base goods: ₹318,547
  - Labour: 534 minutes @ ₹750/hr = ₹6,675
  - Freight: ₹12,742 (4% on ₹318,547)
  - Grand total: ₹337,964
- **Voiceover**: 
  > *"Every line in the quote cites exact catalog SKUs, finish uplift basis points, and quantity discounts. Integer INR arithmetic with half-up rounding guarantees exact reconciliation to the last rupee without floating-point drift."*

---

### 5. Bonus Tracks & Determinism Proof (4:00 - 5:00)
- **Action**: 
  1. Show `OUTPUT/ROOM-01/layout.dxf` in a CAD viewer or text format showcasing layers (`WALLS`, `DOORS`, `EGRESS`, `FURNITURE`).
  2. Show `rulebound/api.py` with Microsoft Entra ID JWT verification.
  3. Run the official determinism checker:
     ```bash
     python RuleBound_Round1_Release/tools/check_determinism.py --command 'python runner.py --input \"{input}\" --output \"{output}\"' --input RuleBound_Round1_Release/data --work-dir .determinism-check
     ```
- **Voiceover**: 
  > *"All 15 generated files are 100% byte-identical across repeat runs. The solution includes full AutoCAD DXF exports and an Azure-ready REST microservice secured by Entra ID. Thank you."*
