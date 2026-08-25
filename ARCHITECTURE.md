# RuleBound System Architecture

RuleBound bridges generative spatial layout proposal with pure, byte-identical deterministic constraint enforcement and line-traceable pricing for commercial furniture fit-outs.

---

## 1. System Overview & Component Boundaries

```text
┌────────────────────────┐        Candidate Proposal (Inbound Contract)       ┌────────────────────────┐
│    Generative Layer    │ ───────────────────────────────────────────────────► │  Deterministic Verifier│
│ (Spatial Layout Synth) │ ◄─────────────────────────────────────────────────── │   (Geometry & Rules)   │
└────────────────────────┘      Verification Feedback (Outbound Contract)       └───────────┬────────────┘
                                                                                            │
                                                                                            ▼
┌────────────────────────┐       Byte-Identical Reconciled Quote Output        ┌────────────────────────┐
│  Committed Artifacts   │ ◄─────────────────────────────────────────────────── │   Pricing Engine       │
│ (layout.json, quote)   │                                                      │ (Integer INR / Traces) │
└────────────────────────┘                                                      └────────────────────────┘
```

The system is decoupled into four discrete layers:
1. **Generative Layout Layer (`rulebound/generator.py`)**: Synthesizes top-down 2D spatial layouts matching room capacity and brief requirements.
2. **Spatial Geometry & Constraint Verifier (`rulebound/geometry.py`, `rulebound/constraints.py`)**: Executes continuous collision detection (SAT), door swing arc clearances, and egress corridor safety envelopes.
3. **Arbitration Engine (`rulebound/arbitration.py`)**: A bounded state machine that mediates conflicts, executes ranked geometric repairs, and guarantees monotonic energy reduction.
4. **Deterministic Pricing Engine (`rulebound/pricing.py`)**: Pure integer INR calculation engine enforcing quantity discounts, finish uplifts, labor bands, and freight tiers with zero floating-point drift.

---

## 2. Arbitration

### 2.1. Seam Object Contracts
The boundary between creative proposal and deterministic verification is mediated by two strictly typed JSON contracts:

**Inbound Contract (`CandidateProposal`):**
```json
{
  "room_id": "ROOM-01",
  "iteration": 1,
  "placements": [
    {
      "placement_id": "P001",
      "sku": "NW-DES-003",
      "finish_id": "F03",
      "x_mm": 200.0,
      "y_mm": 2600.0,
      "rotation_deg": 0.0
    }
  ]
}
```

**Outbound Contract (`VerificationFeedback`):**
```json
{
  "status": "invalid",
  "energy_score": 1420.5,
  "violations": [
    {
      "violation_id": "V001",
      "rule_id": "RB-GEO-002",
      "message": "Placement P001 obstructs marked egress route.",
      "affected_placement_ids": ["P001"],
      "measured": { "distance_to_egress_centerline_mm": 410.2 },
      "required": { "min_clearance_radius_mm": 550.0 },
      "repair_options": [
        { "action": "shift_along_normal", "dx_mm": 0.0, "dy_mm": 200.0, "priority": 1 }
      ]
    }
  ]
}
```

### 2.2. Decision Boundaries & Irreversible Control Hand-Off
- **Model Decision Space**: The generative planner proposes placement coordinates $(x, y)$, rotations $\theta \in \{0^\circ, 90^\circ, 180^\circ, 270^\circ\}$, SKU selections, and finish pairings.
- **Irreversible Hand-Off**: The moment a candidate layout crosses into the Arbitration Seam, **control passes permanently to deterministic code**. No probabilistic model, LLM, or heuristic can soften rules, bypass verifications, or participate in pricing.

### 2.3. Termination Proof & Strictly Decreasing Lyapunov Measure
To prevent non-terminating cycles, the arbitration loop is governed by an upper iteration bound $K_{\max} = 50$ and a strictly decreasing energy metric $\Phi(L)$:

$$\Phi(L) = 1000 \cdot |V| + \sum_{v \in V_{\text{overlap}}} \text{depth}(v) + \sum_{v \in V_{\text{clearance}}} \text{deficit}(v)$$

**Monotonicity & Repair Operations:**
1. **Micro-Nudge**: Displaces overlapping items along the Separating Axis Theorem (SAT) minimum translation vector by $\text{penetration\_depth} + 100\text{mm}$, reducing $\Phi(L)$.
2. **Egress Relocation**: Repositions items infringing upon the $1100\text{mm}$ egress corridor into verified open space.
3. **Plateau Detection & Pruning**: If $\Phi(L_{t+1}) \ge \Phi(L_t)$ for 3 consecutive passes, lowest-priority items (accessories $\to$ storage) are pruned, strictly reducing the search dimension.

### 2.4. Escalation Protocol for Unsatisfiable Rooms
When a room is geometrically overconstrained and cannot satisfy the brief within $K_{\max}$ passes:
1. `layout.json` is emitted with `status: "unsatisfiable"` and structured `ESC-*` violation objects.
2. The customer receives actionable trade-offs: e.g., *"Reduce capacity from 18 to 14"* or *"Select compact 1200mm desks"*.
3. `quote.json` is saved with `status: "blocked"` under `RB-PRC-013`, preventing unverified orders from reaching production.

---

## 3. Pricing Engine & Mathematical Determinism

All calculations utilize integer INR and Basis Points (`100 bps = 1%`). Division uses Banker's Round Half-Up arithmetic (`Decimal(val).quantize(Decimal('1'), ROUND_HALF_UP)`):

- **Line Net Goods**: $\text{base} + \text{round\_half\_up}(\text{base} \times \text{uplift\_bps} / 10000) - \text{round\_half\_up}(\text{base} \times \text{discount\_bps} / 10000)$.
- **Labor**: Tiered rates (₹900/hr $\le 240\text{m}$, ₹800/hr $241-480\text{m}$, ₹750/hr $>480\text{m}$) applied across quote minutes.
- **Freight**: Tiered rates (₹5,000 $\le ₹100\text{k}$, ₹9,000 $₹100\text{k}-₹250\text{k}$, $400\text{ bps}$ $>₹250\text{k}$).
- **Line-Level Traceability**: Every figure contains explicit rule citations (`CATALOG`, `RB-PRC-009` through `RB-PRC-012`).

---

## 4. Bonus Integrations

- **AutoCAD DXF Exporter (`rulebound/dxf.py`)**: Exports complete multi-layer 2D CAD layouts (`WALLS`, `DOORS`, `EGRESS`, `FURN_DESK`, `FURN_CHAIR`, `ANNOTATIONS`).
- **Azure Cloud Service with Microsoft Entra ID (`rulebound/api.py`, `azure-deploy.bicep`)**: Production FastAPI REST microservice secured with Entra ID Bearer JWT validation.
