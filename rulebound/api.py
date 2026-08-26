from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from rulebound.arbitration import ArbitrationEngine, compute_energy_metric
from rulebound.constraints import verify_spatial_constraints
from rulebound.dxf import export_layout_to_dxf
from rulebound.generator import LayoutGenerator
from rulebound.loader import load_asset_pack
from rulebound.models import Placement, RoomSpec
from rulebound.pricing import price_placements

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "RuleBound_Round1_Release/data"
UI_HTML_PATH = ROOT_DIR / "rulebound/ui.html"

app = FastAPI(
    title="RuleBound Enterprise Platform",
    version="1.0.0",
    description="Deterministic Layout Verification, Arbitration, and Pricing Engine for Northwind Furnishings.",
)

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "rulebound-api")
REQUIRE_AUTH = os.getenv("REQUIRE_ENTRA_AUTH", "false").lower() == "true"


def verify_entra_id_token(authorization: str = Header(None)) -> dict[str, Any]:
    if not REQUIRE_AUTH:
        return {"sub": "rishi@northwind.com", "roles": ["RuleBound.Architect"]}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Microsoft Entra ID Bearer token.",
        )

    token = authorization.split(" ")[1]
    try:
        import jwt
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Entra ID Token: {exc}",
        )


class LayoutRequest(BaseModel):
    room_spec: dict[str, Any]
    pack_dir: str = str(DATA_DIR)


class PlacementDTO(BaseModel):
    placement_id: str
    sku: str
    finish_id: str
    x_mm: float
    y_mm: float
    rotation_deg: float


class VerifyRequest(BaseModel):
    room_spec: dict[str, Any]
    placements: list[PlacementDTO]
    pack_dir: str = str(DATA_DIR)


class PricingRequest(BaseModel):
    room_id: str
    placements: list[PlacementDTO]
    pack_dir: str = str(DATA_DIR)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "RuleBound Enterprise Engine", "version": "1.0.0"}


@app.get("/api/v1/rooms")
def list_rooms():
    pack = load_asset_pack(DATA_DIR)
    return [
        {
            "room_id": r.room_id,
            "name": r.name,
            "capacity": r.capacity,
            "boundary_mm": r.boundary_mm,
            "doors": [d.__dict__ for d in r.doors],
            "windows": [w.__dict__ for w in r.windows],
            "egress": {
                "from_door_id": r.egress.from_door_id,
                "to_point_mm": r.egress.to_point_mm,
                "min_width_mm": r.egress.min_width_mm,
            },
            "brief": pack.briefs.get(r.room_id, ""),
        }
        for r in sorted(pack.rooms, key=lambda x: x.room_id)
    ]


@app.get("/api/v1/room/{room_id}/data")
def get_room_full_data(room_id: str):
    pack = load_asset_pack(DATA_DIR)
    room = pack.rooms_by_id.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")

    generator = LayoutGenerator()
    placements = generator.generate_candidate_layout(room, pack)
    arbitrator = ArbitrationEngine()
    layout_res = arbitrator.arbitrate(room, placements, pack)
    quote_res = price_placements(room_id, layout_res.placements, pack)

    catalog_dict = {
        item.sku: {
            "sku": item.sku,
            "family": item.family,
            "name": item.name,
            "width": item.dimensions_mm.width,
            "depth": item.dimensions_mm.depth,
            "height": item.dimensions_mm.height,
            "price": item.list_price_inr,
            "finishes": item.compatible_finish_ids,
        }
        for item in pack.catalog
    }

    return {
        "room": {
            "room_id": room.room_id,
            "name": room.name,
            "capacity": room.capacity,
            "boundary_mm": room.boundary_mm,
            "doors": [d.__dict__ for d in room.doors],
            "windows": [w.__dict__ for w in room.windows],
            "egress": {
                "from_door_id": room.egress.from_door_id,
                "to_point_mm": room.egress.to_point_mm,
                "min_width_mm": room.egress.min_width_mm,
            },
            "brief": pack.briefs.get(room.room_id, ""),
        },
        "layout": layout_res.to_dict(),
        "quote": quote_res.to_dict(),
        "catalog": catalog_dict,
    }


@app.get("/api/v1/room/{room_id}/dxf")
def download_dxf(room_id: str):
    dxf_path = ROOT_DIR / f"OUTPUT/{room_id}/layout.dxf"
    pack = load_asset_pack(DATA_DIR)
    room = pack.rooms_by_id.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    gen = LayoutGenerator()
    placements = gen.generate_candidate_layout(room, pack)
    export_layout_to_dxf(room, placements, pack, dxf_path)

    return FileResponse(
        dxf_path,
        media_type="application/dxf",
        filename=f"{room_id}_layout.dxf",
    )


@app.post("/api/v1/layout/synthesize")
def synthesize_layout(req: LayoutRequest, user=Depends(verify_entra_id_token)):
    pack = load_asset_pack(req.pack_dir)
    room = pack.rooms_by_id.get(req.room_spec.get("room_id", ""))
    if not room:
        raise HTTPException(status_code=404, detail="Room specification not found in asset pack.")
    generator = LayoutGenerator()
    placements = generator.generate_candidate_layout(room, pack)
    arbitrator = ArbitrationEngine()
    result = arbitrator.arbitrate(room, placements, pack)
    return result.to_dict()


@app.post("/api/v1/layout/verify")
def verify_layout(req: VerifyRequest, user=Depends(verify_entra_id_token)):
    pack = load_asset_pack(req.pack_dir)
    room = pack.rooms_by_id.get(req.room_spec.get("room_id", ""))
    if not room:
        raise HTTPException(status_code=404, detail="Room specification not found in asset pack.")
    placements = [
        Placement(
            placement_id=p.placement_id,
            sku=p.sku,
            finish_id=p.finish_id,
            x_mm=p.x_mm,
            y_mm=p.y_mm,
            rotation_deg=p.rotation_deg,
        )
        for p in req.placements
    ]
    violations = verify_spatial_constraints(room, placements, pack)
    return {
        "room_id": room.room_id,
        "is_valid": len(violations) == 0,
        "violation_count": len(violations),
        "energy_score": compute_energy_metric(violations),
        "violations": [v.to_dict() for v in violations],
    }


@app.post("/api/v1/quote/calculate")
def calculate_quote(req: PricingRequest, user=Depends(verify_entra_id_token)):
    pack = load_asset_pack(req.pack_dir)
    placements = [
        Placement(
            placement_id=p.placement_id,
            sku=p.sku,
            finish_id=p.finish_id,
            x_mm=p.x_mm,
            y_mm=p.y_mm,
            rotation_deg=p.rotation_deg,
        )
        for p in req.placements
    ]
    quote = price_placements(req.room_id, placements, pack)
    return quote.to_dict()


@app.get("/", response_class=HTMLResponse)
def index_visualizer():
    if UI_HTML_PATH.exists():
        return HTMLResponse(content=UI_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>RuleBound Studio UI</h1>")
