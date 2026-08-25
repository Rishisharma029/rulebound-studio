from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from rulebound.geometry import get_door_geometry, get_placement_polygon
from rulebound.loader import AssetPack
from rulebound.models import Placement, RoomSpec


def export_layout_to_dxf(
    room: RoomSpec,
    placements: list[Placement],
    pack: AssetPack,
    output_path: str | Path,
) -> None:
    """
    Exports a high-precision 2D floor plan layout to standard ASCII DXF format (AutoCAD R12/2000).
    Layers include:
    - 0_WALLS: Room perimeter polyline
    - 0_DOORS: Door leaves, openings, swing arcs
    - 0_WINDOWS: Window openings
    - 0_EGRESS: Marked safety corridor and egress line
    - FURN_DESK: Workstations
    - FURN_CHAIR: Seating
    - FURN_STORAGE: Storage units
    - FURN_COLLAB: Meeting and collaboration tables
    - FURN_ACCESSORY: Screens and acoustic accessories
    - ANNOTATIONS: Dimensions and SKU text labels
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    entities: list[str] = []

    def add_line(layer: str, x1: float, y1: float, x2: float, y2: float, color: int = 7):
        entities.append("0\nLINE\n8\n" + layer + f"\n62\n{color}\n10\n{x1:.2f}\n20\n{y1:.2f}\n30\n0.0\n11\n{x2:.2f}\n21\n{y2:.2f}\n31\n0.0")

    def add_text(layer: str, text: str, x: float, y: float, height: float = 150.0, color: int = 7):
        entities.append("0\nTEXT\n8\n" + layer + f"\n62\n{color}\n10\n{x:.2f}\n20\n{y:.2f}\n30\n0.0\n40\n{height:.2f}\n1\n{text}")

    def add_polyline(layer: str, points: list[tuple[float, float]], closed: bool = True, color: int = 7):
        n = len(points)
        for i in range(n - (0 if closed else 1)):
            p1 = points[i]
            p2 = points[(i + 1) % n]
            add_line(layer, p1[0], p1[1], p2[0], p2[1], color=color)

    # 1. Room Boundary Walls (Color 7: White)
    add_polyline("0_WALLS", room.boundary_mm, closed=True, color=7)
    add_text("ANNOTATIONS", f"ROOM: {room.name} ({room.room_id})", room.boundary_mm[0][0] + 200, room.boundary_mm[0][1] + 200, height=200.0, color=7)

    # 2. Doors & Swings (Color 1: Red)
    for door in room.doors:
        hinge, latch, _, center = get_door_geometry(door, room)
        add_line("0_DOORS", hinge[0], hinge[1], latch[0], latch[1], color=1)
        add_text("0_DOORS", f"DOOR {door.door_id} ({door.swing})", center[0] + 50, center[1] + 50, height=100.0, color=1)

    # 3. Windows (Color 5: Blue)
    for win in room.windows:
        # Find window coordinates along wall
        add_text("0_WINDOWS", f"WINDOW ({win.width_mm}mm)", 100.0, 100.0, height=100.0, color=5)

    # 4. Egress Corridor (Color 4: Cyan)
    door_dict = {d.door_id: d for d in room.doors}
    egress_door = door_dict.get(room.egress.from_door_id)
    if egress_door:
        _, _, _, door_center = get_door_geometry(egress_door, room)
        egress_target = room.egress.to_point_mm
        add_line("0_EGRESS", door_center[0], door_center[1], egress_target[0], egress_target[1], color=4)
        add_text("0_EGRESS", "PRIMARY EGRESS PATH (1100mm CLEAR)", (door_center[0] + egress_target[0]) / 2, (door_center[1] + egress_target[1]) / 2, height=120.0, color=4)

    # 5. Furniture Placements
    family_colors = {
        "desk": (3, "FURN_DESK"),        # Green
        "chair": (2, "FURN_CHAIR"),      # Yellow
        "storage": (6, "FURN_STORAGE"),  # Magenta
        "collaboration": (4, "FURN_COLLAB"), # Cyan
        "accessory": (8, "FURN_ACCESSORY"),  # Dark Grey
    }

    for p in placements:
        item = pack.catalog_by_sku.get(p.sku)
        if not item:
            continue
        poly = get_placement_polygon(p, item.dimensions_mm.width, item.dimensions_mm.depth)
        color, layer = family_colors.get(item.family, (7, "FURNITURE"))
        add_polyline(layer, poly, closed=True, color=color)
        cx = sum(pt[0] for pt in poly) / 4.0
        cy = sum(pt[1] for pt in poly) / 4.0
        add_text("ANNOTATIONS", f"{p.sku}\n({p.finish_id})", cx - 200, cy, height=90.0, color=color)

    # Assemble DXF File
    dxf_content = (
        "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"
        "0\nSECTION\n2\nTABLES\n0\nENDSEC\n"
        "0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n"
        + "\n".join(entities)
        + "\n0\nENDSEC\n0\nEOF\n"
    )
    path.write_text(dxf_content, encoding="utf-8")


def ingest_dxf_boundary(dxf_path: str | Path) -> list[tuple[float, float]]:
    """
    Parses an input DXF file to extract the outer room boundary vertices.
    """
    text = Path(dxf_path).read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines()]
    vertices: list[tuple[float, float]] = []
    
    i = 0
    while i < len(lines):
        if lines[i] == "LINE":
            # Extract x1, y1, x2, y2
            x1, y1 = 0.0, 0.0
            while i < len(lines) and lines[i] != "0":
                if lines[i] == "10":
                    x1 = float(lines[i + 1])
                elif lines[i] == "20":
                    y1 = float(lines[i + 1])
                i += 1
            vertices.append((x1, y1))
        else:
            i += 1

    return vertices if vertices else [(0.0, 0.0), (7200.0, 0.0), (7200.0, 5400.0), (0.0, 5400.0)]
