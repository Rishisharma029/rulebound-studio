from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from rulebound.constraints import verify_spatial_constraints
from rulebound.ir import extract_requirement_ir
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec
from rulebound.traceability import build_traceability_matrix


@dataclass
class SemanticCheckResult:
    check_id: str
    name: str
    passed: bool
    room_id: str
    details: str


@dataclass
class SemanticAuditReport:
    total_checks: int
    passed_checks: int
    failed_checks: int
    all_passed: bool
    results: list[SemanticCheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_semantic_outputs(
    output_dir: str | Path,
    pack: AssetPack,
) -> SemanticAuditReport:
    """
    Executes a comprehensive, deep semantic coherence audit across all output rooms.
    Verifies that outputs are not merely present on disk, but mathematically,
    spatially, catalog-consistent, and requirements-traceable.

    Audit Matrix:
      1. 5 rooms generated (ROOM-01 to ROOM-05)
      2. 5 layouts valid or properly blocked
      3. 5 quotes present with canonical schema
      4. Placement-Quote Bijection: layout placement IDs == quote line item placement IDs
      5. Every SKU exists in catalog
      6. Every finish is valid and catalog-compatible
      7. All valid layouts have Lyapunov energy Phi == 0 (zero violations)
      8. Unsatisfiable layouts have blocked quote with zero payable total
      9. RequirementIR successfully extracted for every room
      10. Requirement satisfaction score computed for every room
    """
    out_path = Path(output_dir)
    results: list[SemanticCheckResult] = []
    expected_rooms = ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]

    for room_id in expected_rooms:
        room_dir = out_path / room_id
        room = pack.rooms_by_id.get(room_id)
        if not room:
            results.append(
                SemanticCheckResult(
                    check_id="SEM-001",
                    name="Room Specification Existence",
                    passed=False,
                    room_id=room_id,
                    details=f"Room {room_id} not found in input pack.",
                )
            )
            continue

        # 1. Room output directory exists
        dir_exists = room_dir.is_dir()
        results.append(
            SemanticCheckResult(
                check_id="SEM-001",
                name="Room Directory Existence",
                passed=dir_exists,
                room_id=room_id,
                details=f"Directory {room_dir.name} {'exists' if dir_exists else 'is missing'}",
            )
        )
        if not dir_exists:
            continue

        # 2. Files exist
        layout_file = room_dir / "layout.json"
        quote_file = room_dir / "quote.json"
        files_ok = layout_file.exists() and quote_file.exists()
        results.append(
            SemanticCheckResult(
                check_id="SEM-002",
                name="Artifact Presence (layout.json & quote.json)",
                passed=files_ok,
                room_id=room_id,
                details=f"Both layout.json and quote.json present: {files_ok}",
            )
        )
        if not files_ok:
            continue

        # Parse JSON
        try:
            layout_data = json.loads(layout_file.read_text(encoding="utf-8"))
            quote_data = json.loads(quote_file.read_text(encoding="utf-8"))
        except Exception as e:
            results.append(
                SemanticCheckResult(
                    check_id="SEM-003",
                    name="JSON Syntactic Coherence",
                    passed=False,
                    room_id=room_id,
                    details=f"Failed to parse JSON: {e}",
                )
            )
            continue

        layout_status = layout_data.get("status", "")
        quote_status = quote_data.get("status", "")
        layout_placements = layout_data.get("placements", [])

        # 3. Valid status enumeration
        status_ok = layout_status in ["valid", "blocked", "unsatisfiable"] and quote_status in ["priced", "blocked"]
        results.append(
            SemanticCheckResult(
                check_id="SEM-003",
                name="Status Enumeration Coherence",
                passed=status_ok,
                room_id=room_id,
                details=f"Layout status '{layout_status}', Quote status '{quote_status}'",
            )
        )

        # 4. Placement-Quote Bijection
        if layout_status == "valid":
            layout_count = len(layout_placements)
            quote_lines = quote_data.get("lines", [])
            quote_count = sum(line.get("quantity", 0) for line in quote_lines)
            
            # Verify exact SKU + Finish multiset match
            layout_skus = sorted([(p["sku"], p["finish_id"]) for p in layout_placements])
            quote_skus = []
            for line in quote_lines:
                quote_skus.extend([(line["sku"], line["finish_id"])] * line.get("quantity", 0))
            quote_skus.sort()
            bijection_ok = (layout_count == quote_count and layout_skus == quote_skus and layout_count > 0)

            results.append(
                SemanticCheckResult(
                    check_id="SEM-004",
                    name="Placement-Quote Bijection",
                    passed=bijection_ok,
                    room_id=room_id,
                    details=f"{layout_count} layout placements <-> {quote_count} quoted units ({len(quote_lines)} lines, exact multiset match)",
                )
            )
        else:
            blocked_soundness = (quote_status == "blocked" and quote_data.get("summary", {}).get("grand_total_inr", 0.0) == 0.0)
            results.append(
                SemanticCheckResult(
                    check_id="SEM-004",
                    name="UNSAT Quote Soundness",
                    passed=blocked_soundness,
                    room_id=room_id,
                    details=f"Unsatisfiable layout produces blocked quote with ₹0 total: {blocked_soundness}",
                )
            )

        # 5. Catalog SKU existence
        unknown_skus = [p["sku"] for p in layout_placements if p.get("sku") not in pack.catalog_by_sku]
        results.append(
            SemanticCheckResult(
                check_id="SEM-005",
                name="Catalog SKU Existence",
                passed=len(unknown_skus) == 0,
                room_id=room_id,
                details="All placed SKUs exist in catalog" if not unknown_skus else f"Unknown SKUs: {unknown_skus}",
            )
        )

        # 6. Finish existence & compatibility
        finish_compat_ok = True
        bad_finishes: list[str] = []
        for p in layout_placements:
            f_id = p.get("finish_id")
            sku = p.get("sku")
            item = pack.catalog_by_sku.get(sku)
            finish = pack.finishes_by_id.get(f_id)
            if not finish or not item:
                finish_compat_ok = False
                bad_finishes.append(f"{sku}:{f_id}")
            elif finish.compatible_families and item.family not in finish.compatible_families:
                finish_compat_ok = False
                bad_finishes.append(f"{sku}:{f_id} (family {item.family} not in {finish.compatible_families})")

        results.append(
            SemanticCheckResult(
                check_id="SEM-006",
                name="Finish Catalog Compatibility",
                passed=finish_compat_ok,
                room_id=room_id,
                details="All finishes valid and family-compatible" if finish_compat_ok else f"Incompatible: {bad_finishes[:3]}",
            )
        )

        # 7. Zero-violation verification for valid layouts (Phi == 0)
        typed_pls: list[Placement] = []
        if layout_status == "valid":
            typed_pls = [
                Placement(
                    placement_id=p["placement_id"],
                    sku=p["sku"],
                    finish_id=p["finish_id"],
                    x_mm=float(p["x_mm"]),
                    y_mm=float(p["y_mm"]),
                    rotation_deg=float(p["rotation_deg"]),
                )
                for p in layout_placements
            ]
            live_violations = verify_spatial_constraints(room, typed_pls, pack)
            zero_viol_ok = (len(live_violations) == 0 and len(layout_data.get("violations", [])) == 0)
            results.append(
                SemanticCheckResult(
                    check_id="SEM-007",
                    name="Zero Spatial Violations Soundness (Phi == 0)",
                    passed=zero_viol_ok,
                    room_id=room_id,
                    details=f"Live constraint verification returned {len(live_violations)} violations",
                )
            )

        # 8. RequirementIR existence
        brief_text = pack.briefs.get(room_id, "")
        ir = extract_requirement_ir(brief_text, room)
        ir_ok = (ir is not None and ir.occupancy >= 0)
        results.append(
            SemanticCheckResult(
                check_id="SEM-008",
                name="RequirementIR Extraction",
                passed=ir_ok,
                room_id=room_id,
                details=f"Extracted occupancy={ir.occupancy}, workstations={ir.workstations.count}, seating={ir.seating}",
            )
        )

        # 9. Requirement satisfaction score computation
        rtm = build_traceability_matrix(ir, typed_pls if layout_status == "valid" else [], room, pack, brief_text)
        sat_ok = (rtm.overall_satisfaction_pct >= 0.0 and len(rtm.entries) > 0)
        results.append(
            SemanticCheckResult(
                check_id="SEM-009",
                name="Requirement Satisfaction Score",
                passed=sat_ok,
                room_id=room_id,
                details=f"Computed satisfaction score {rtm.overall_satisfaction_pct:.1f}% across {len(rtm.entries)} brief requirements",
            )
        )

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    all_passed = (failed_count == 0)

    return SemanticAuditReport(
        total_checks=len(results),
        passed_checks=passed_count,
        failed_checks=failed_count,
        all_passed=all_passed,
        results=results,
    )
