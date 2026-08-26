# RuleBound Round 1: 5-Minute Video Recording Script

This script gives you the exact chronological narrative to record the 5-minute competition video.

> [!IMPORTANT]
> **Video Focus**: Spend your time on the **Trust Boundary**, the **9-stage terminal arbitration demo (`python demo.py`)**, and the **Interactive Visualizer (`http://127.0.0.1:8080`)**. Do NOT waste time navigating raw Swagger endpoints in the video — the judges want to see the **35-point deterministic arbitration state machine and mathematical pricing proof**.

---

## ⏱️ Video Breakdown & Outline

| Timestamp | Segment | Key Screen Visual | Voiceover / Action |
|---|---|---|---|
| **0:00 – 0:45** | **1. Architecture & Trust Boundary** | `ARCHITECTURE.md` + UI Trust Boundary modal | Explain the Northwind domain, seam contract, and strict separation between probabilistic generation and the deterministic core. |
| **0:45 – 2:15** | **2. Terminal Arbitration Demo** | Run `python demo.py` | Walk through the 9 stages: initial layout → injected violation → candidate proposal → rejected candidate → accepted candidate → Lyapunov Φ convergence → quote reconciliation. |
| **2:15 – 3:45** | **3. Interactive CAD & Pricing Studio** | Browser at `http://127.0.0.1:8080` | Demonstrate live violation injection (`DEMO MODE`), auditable 8-rule table, Lyapunov trace feed, and click-to-inspect mathematical price provenance modal. |
| **3:45 – 4:30** | **4. Unsatisfiable Case & Trade-offs** | UI `DEMO MODE → Trigger Unsatisfiable Case` | Show `ESC-001` escalation, `RB-PRC-013` block, and one-click architectural trade-offs. |
| **4:30 – 5:00** | **5. Determinism Check & Conclusion** | Terminal: `validate_output.py` & `check_determinism.py` | Prove 100% byte-identical determinism across all 15 output files. |

---

## 🎬 Detailed Voiceover & Actions

### 1. Introduction & Trust Boundary (0:00 – 0:45)
- **Visual**: Show `ARCHITECTURE.md` and the **Trust Boundary** modal on `http://127.0.0.1:8080`.
- **Narration**:
  > *"Welcome to RuleBound: The Sealed Build Challenge. In commercial office space planning, sales briefs often fail due to geometric clearance errors and pricing miscalculations. Our submission establishes an irreversible Deterministic Trust Boundary: probabilistic layers only propose candidate layouts via strongly-typed Seam Contracts, while all geometric verification, constraint arbitration, and integer INR pricing are executed by a pure deterministic engine with zero LLM in the loop."*

---

### 2. Live Terminal Arbitration (`python demo.py`) (0:45 – 2:15)
- **Visual**: Open terminal and run:
  ```powershell
  python demo.py
  ```
- **Narration**:
  > *"To demonstrate our 35-point arbitration system, let's run our dedicated one-command demonstration.
  > 
  > In Stage 1, we generate an initial valid layout with an energy metric Φ = 0.0.
  > In Stage 2, we deliberately inject a multi-constraint violation on Workstation P001, pushing it within 50mm of the perimeter wall and into direct SAT collision with P002.
  > In Stage 3, the verifier catches RB-GEO-005 wall proximity and RB-GEO-006 overlap, causing the Lyapunov energy metric Φ to spike to 4,080.
  > In Stage 4 and 5, our arbitration state machine evaluates structured candidate repairs. Candidate 1 attempts a naive X-displacement, but is REJECTED because Φ remains at 4,080.
  > In Stage 6, Candidate 3 executes an orthogonal SAT separation vector and is ACCEPTED with ΔΦ = -1,353.9.
  > Over bounded passes, the Lyapunov energy decreases monotonically to exactly 0.0, restoring 100% geometric compliance and regenerating an auditable INR quote."*

---

### 3. Interactive CAD & Pricing Studio (2:15 – 3:45)
- **Visual**: Switch to browser at `http://127.0.0.1:8080`.
- **Action**:
  1. Click **`DEMO MODE → Inject Overlap`**: show Workstation turning bright red (`⚠ P001`), pipeline stepper changing to `VIOLATIONS / QUOTE STALE`.
  2. Click **`8/8 Rules Tab`**: show `RB-GEO-006` measured overlap against the required 0 mm² threshold.
  3. Click **`⚖ Run Arbitration`**: show layout snap into compliance, trace feed logging candidate decisions, and Φ → 0.0.
  4. Click **`Line Trace Tab`** and click on `NW-CHA-004`: show the **Price Provenance Modal** detailing quantity tier discount (700 bps), finish uplift (750 bps), and exact integer arithmetic.
- **Narration**:
  > *"Our interactive studio exposes every decision. When we inject an overlap, the CAD canvas renders high-contrast hazard highlights and invalidates the quote state. Clicking the 8-Rule Auditable Verifier reveals exact measured clearances against required tolerances. Running arbitration smoothly repairs the layout, and clicking any quote line item reveals the full arithmetic provenance with exact basis points and half-up rounding."*

---

### 4. Unsatisfiable Escalation & Trade-offs (3:45 – 4:30)
- **Visual**: In `http://127.0.0.1:8080`, click **`DEMO MODE → Trigger Unsatisfiable Case`**.
- **Action**: Show red banner `⚠ UNSATISFIABLE CONFIGURATION (RB-PRC-013 BLOCKED)` with suggested trade-off buttons `[ ⚡ Reduce Occupancy ]` and `[ ⚡ Downsize Desk SKU ]`.
- **Narration**:
  > *"When a client brief is geometrically impossible — such as requesting 18 seats in an area that would obstruct the 1100mm egress corridor — the system exhausts its bounded search and enters an explicit Unsatisfiable state. Rather than silently failing or hallucinating invalid geometry, it blocks quote issuance under rule RB-PRC-013 and presents human-in-the-loop architectural trade-offs."*

---

### 5. Determinism Proof & Conclusion (4:30 – 5:00)
- **Visual**: Open terminal and run:
  ```powershell
  python RuleBound_Round1_Release/tools/validate_output.py OUTPUT
  python RuleBound_Round1_Release/tools/check_determinism.py --command "python runner.py --input \"{input}\" --output \"{output}\"" --input RuleBound_Round1_Release/data --work-dir .determinism-check
  ```
- **Narration**:
  > *"Finally, we run the official Round 1 validator and determinism test. The validator reports 100% compliance across all 5 benchmark rooms, and the determinism checker confirms that all 15 output files are byte-identical across repeat runs. The submission includes full AutoCAD DXF exports and an Azure Entra ID microservice. Thank you."*
