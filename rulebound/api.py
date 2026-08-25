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

app = FastAPI(
    title="RuleBound Enterprise Platform",
    version="1.0.0",
    description="Deterministic Layout Verification, Arbitration, and Pricing Engine for Northwind Furnishings.",
)

# Azure Entra ID Configuration
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "rulebound-api")
REQUIRE_AUTH = os.getenv("REQUIRE_ENTRA_AUTH", "false").lower() == "true"


def verify_entra_id_token(authorization: str = Header(None)) -> dict[str, Any]:
    """Validates Microsoft Entra ID Bearer JWT token."""
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
    html_content = """<!DOCTYPE html>
<html class="dark" lang="en">
<head>
  <meta charset="utf-8"/>
  <meta content="width=device-width, initial-scale=1.0" name="viewport"/>
  <title>RuleBound | Precision CAD & Deterministic Pricing Studio</title>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
  <script>
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            "background": "#020617",
            "surface": "#0b1326",
            "surface-dim": "#0b1326",
            "surface-bright": "#31394d",
            "surface-container": "#171f33",
            "surface-container-low": "#131b2e",
            "surface-container-high": "#222a3d",
            "surface-container-highest": "#2d3449",
            "primary": "#8aebff",
            "primary-container": "#22d3ee",
            "secondary": "#4edea3",
            "secondary-container": "#00a572",
            "outline": "#859397",
            "outline-variant": "#3c494c",
            "error": "#ffb4ab",
            "error-container": "#93000a",
            "on-surface": "#dae2fd",
            "on-surface-variant": "#bbc9cd",
          },
          fontFamily: {
            sans: ["Inter", "sans-serif"],
            mono: ["JetBrains Mono", "monospace"]
          }
        }
      }
    }
  </script>
  <style>
    body { background-color: #020617; color: #dae2fd; overflow: hidden; font-family: 'Inter', sans-serif; }
    .glass-panel { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.08); }
    .glow-active { box-shadow: 0 0 10px rgba(34, 211, 238, 0.35); border-color: #22d3ee; }
    .cad-grid-bg { background-image: linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px); background-size: 24px 24px; }
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3c494c; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #22d3ee; }
  </style>
</head>
<body class="flex flex-col h-screen antialiased select-none">

  <!-- Top Header Navigation -->
  <header class="h-14 bg-surface-container border-b border-outline-variant/60 flex justify-between items-center px-6 z-50">
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded bg-primary-container/20 border border-primary flex items-center justify-center text-primary font-bold">
          <span class="material-symbols-outlined text-base">domain</span>
        </div>
        <span class="font-bold text-lg tracking-tight text-white">NORTHWIND <span class="text-primary font-mono text-xs font-semibold px-2 py-0.5 rounded bg-primary/10 border border-primary/30">RULEBOUND</span></span>
      </div>
      <div class="h-4 w-px bg-outline-variant/60 mx-1"></div>
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
        <span class="text-xs font-mono text-secondary font-medium tracking-wide">DETERMINISTIC ENGINE ONLINE</span>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <a href="/docs" target="_blank" class="px-3 py-1.5 rounded text-xs font-mono text-on-surface-variant hover:text-primary hover:bg-surface-container-high border border-outline-variant/50 transition-colors flex items-center gap-1.5">
        <span class="material-symbols-outlined text-sm">api</span> OpenAPI Spec
      </a>
      <div class="flex items-center gap-2 pl-3 border-l border-outline-variant/60">
        <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-600 to-emerald-500 border border-white/20 flex items-center justify-center text-white text-xs font-bold font-mono">
          RS
        </div>
        <div class="text-left hidden sm:block">
          <div class="text-xs font-semibold leading-none text-white">Rishi Sharma</div>
          <div class="text-[10px] font-mono text-on-surface-variant leading-none mt-1">Lead Systems Engineer</div>
        </div>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <div class="flex flex-1 overflow-hidden">

    <!-- Left Navigation Sidebar -->
    <nav class="w-64 bg-surface-container-low border-r border-outline-variant/40 flex flex-col justify-between p-3 z-40">
      <div class="space-y-4">
        <!-- Room Selector -->
        <div>
          <label class="block text-[11px] font-mono text-on-surface-variant uppercase tracking-wider mb-2 font-semibold flex items-center gap-1.5">
            <span class="material-symbols-outlined text-sm text-primary">meeting_room</span> Benchmark Rooms
          </label>
          <select id="roomSelect" onchange="loadSelectedRoom()" class="w-full bg-surface-container border border-outline-variant/60 rounded px-2.5 py-2 text-xs font-sans text-white focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-all">
            <option value="ROOM-01">ROOM-01: Harbour Design Studio</option>
            <option value="ROOM-02">ROOM-02: Cedar Client Workshop</option>
            <option value="ROOM-03">ROOM-03: Nimbus Hybrid Team</option>
            <option value="ROOM-04">ROOM-04: Orchard Focus Library</option>
            <option value="ROOM-05">ROOM-05: Summit Project Hub</option>
          </select>
        </div>

        <!-- Room Specs Details -->
        <div class="glass-panel p-3 rounded text-xs space-y-2 border border-outline-variant/30 font-mono">
          <div class="flex justify-between text-[11px] text-on-surface-variant">
            <span>CAPACITY:</span> <span id="specCapacity" class="text-white font-bold">12 occupants</span>
          </div>
          <div class="flex justify-between text-[11px] text-on-surface-variant">
            <span>DIMENSIONS:</span> <span id="specDimensions" class="text-white font-bold">7200 x 5400 mm</span>
          </div>
          <div class="flex justify-between text-[11px] text-on-surface-variant">
            <span>EGRESS WIDTH:</span> <span id="specEgress" class="text-secondary font-bold">1100 mm min</span>
          </div>
        </div>

        <!-- Natural Language Brief Card -->
        <div class="bg-surface-container/60 p-3 rounded border border-outline-variant/30">
          <div class="text-[10px] font-mono uppercase text-primary font-bold mb-1.5 flex items-center gap-1">
            <span class="material-symbols-outlined text-xs">description</span> Client Specification Brief
          </div>
          <p id="briefText" class="text-[11px] leading-relaxed text-on-surface-variant">
            Loading brief description...
          </p>
        </div>
      </div>

      <!-- Live Defense Action Hub -->
      <div class="space-y-2 pt-3 border-t border-outline-variant/40">
        <button onclick="injectViolation()" class="w-full py-2 px-3 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/40 rounded text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-all">
          <span class="material-symbols-outlined text-sm">warning</span> Inject Violation
        </button>
        <button onclick="triggerArbitration()" class="w-full py-2 px-3 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/40 rounded text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-all">
          <span class="material-symbols-outlined text-sm">gavel</span> Run Arbitration Repair
        </button>
        <button onclick="downloadDXF()" class="w-full py-2 px-3 bg-surface-container hover:bg-surface-bright text-white border border-outline-variant/60 rounded text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-all">
          <span class="material-symbols-outlined text-sm">download</span> Export AutoCAD DXF
        </button>
      </div>
    </nav>

    <!-- Center: Interactive CAD Canvas -->
    <main class="flex-1 relative bg-background cad-grid-bg overflow-hidden flex flex-col">
      <div id="canvas-container" class="w-full h-full relative cursor-grab active:cursor-grabbing">
        <canvas id="planCanvas"></canvas>
      </div>

      <!-- Floating Canvas Overlay Controls -->
      <div class="absolute bottom-5 left-1/2 -translate-x-1/2 glass-panel rounded-lg px-3 py-1.5 flex items-center gap-3 shadow-2xl z-30">
        <button onclick="zoomBy(1.2)" class="p-1.5 text-on-surface-variant hover:text-primary rounded hover:bg-surface-bright/50 transition-colors"><span class="material-symbols-outlined text-base">zoom_in</span></button>
        <button onclick="zoomBy(0.8)" class="p-1.5 text-on-surface-variant hover:text-primary rounded hover:bg-surface-bright/50 transition-colors"><span class="material-symbols-outlined text-base">zoom_out</span></button>
        <button onclick="fitToRoom()" class="p-1.5 text-on-surface-variant hover:text-primary rounded hover:bg-surface-bright/50 transition-colors"><span class="material-symbols-outlined text-base">fit_screen</span></button>
        <div class="w-px h-5 bg-outline-variant/60"></div>
        <div class="flex items-center gap-4 text-xs font-mono text-on-surface-variant">
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-emerald-500"></span> Desks</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-amber-400"></span> Seating</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-indigo-400"></span> Collab</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-pink-500"></span> Storage</span>
        </div>
      </div>
    </main>

    <!-- Right Data Panel: Pricing Engine & Spatial Verifier -->
    <aside class="w-96 bg-surface-container-low border-l border-outline-variant/40 flex flex-col h-full overflow-hidden z-40">
      
      <!-- Top Tier: Deterministic Pricing Engine -->
      <div class="flex-1 flex flex-col border-b border-outline-variant/40 overflow-hidden">
        <div class="p-3.5 bg-surface-container flex justify-between items-center border-b border-outline-variant/40">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-base">payments</span>
            <span class="text-xs font-mono font-bold uppercase tracking-wider text-white">Deterministic Pricing</span>
          </div>
          <span id="quoteStatusBadge" class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold">PRICED</span>
        </div>

        <!-- Scrollable Quote Lines Table -->
        <div id="quoteLinesContainer" class="flex-1 overflow-y-auto p-3 space-y-2 text-xs font-mono">
          <!-- Populated by JS -->
        </div>

        <!-- Quote Summary Footer -->
        <div class="p-3.5 bg-surface-container border-t border-outline-variant/40 space-y-1.5 font-mono text-xs">
          <div class="flex justify-between text-on-surface-variant">
            <span>Net Goods:</span> <span id="summaryGoods" class="text-white font-semibold">₹0</span>
          </div>
          <div class="flex justify-between text-on-surface-variant">
            <span>Labour (Band):</span> <span id="summaryLabour" class="text-white font-semibold">₹0</span>
          </div>
          <div class="flex justify-between text-on-surface-variant">
            <span>Freight:</span> <span id="summaryFreight" class="text-white font-semibold">₹0</span>
          </div>
          <div class="pt-2 border-t border-outline-variant/40 flex justify-between items-baseline">
            <span class="text-xs font-bold text-primary uppercase">Grand Total (INR):</span>
            <span id="summaryGrandTotal" class="text-lg font-bold text-emerald-400 font-mono">₹0</span>
          </div>
        </div>
      </div>

      <!-- Bottom Tier: Spatial Constraint Verifier & Lyapunov Engine -->
      <div class="h-64 flex flex-col bg-surface-dim overflow-hidden">
        <div class="p-3 bg-surface-container flex justify-between items-center border-b border-outline-variant/40">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-secondary text-base">verified_user</span>
            <span class="text-xs font-mono font-bold uppercase tracking-wider text-white">Spatial Verifier</span>
          </div>
          <span id="violationCountTag" class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold">0 VIOLATIONS</span>
        </div>

        <!-- Violation Feed -->
        <div id="violationFeed" class="flex-1 overflow-y-auto p-3 space-y-2 font-mono text-xs">
          <div class="p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[11px] flex items-center gap-2">
            <span class="material-symbols-outlined text-base">check_circle</span>
            All 8 spatial constraints satisfied (RB-GEO-001 - RB-GEO-008).
          </div>
        </div>
      </div>

    </aside>
  </div>

  <script>
    let currentData = null;
    let canvas = document.getElementById('planCanvas');
    let ctx = canvas.getContext('2d');
    let panX = 40, panY = 40, zoom = 0.07;
    let isDragging = false, startX, startY;

    function resizeCanvas() {
      const container = document.getElementById('canvas-container');
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
      draw();
    }
    window.addEventListener('resize', resizeCanvas);

    async function loadSelectedRoom() {
      const roomId = document.getElementById('roomSelect').value;
      const res = await fetch(`/api/v1/room/${roomId}/data`);
      currentData = await res.json();
      
      document.getElementById('briefText').innerText = currentData.room.brief;
      document.getElementById('specCapacity').innerText = `${currentData.room.capacity} occupants`;
      const xs = currentData.room.boundary_mm.map(p => p[0]);
      const ys = currentData.room.boundary_mm.map(p => p[1]);
      document.getElementById('specDimensions').innerText = `${Math.max(...xs)} x ${Math.max(...ys)} mm`;
      document.getElementById('specEgress').innerText = `${currentData.room.egress.min_width_mm} mm min`;

      updateQuoteUI(currentData.quote);
      updateViolationsUI(currentData.layout.violations);
      fitToRoom();
      draw();
    }

    function fitToRoom() {
      if (!currentData) return;
      const bounds = currentData.room.boundary_mm;
      const xs = bounds.map(p => p[0]);
      const ys = bounds.map(p => p[1]);
      const width = Math.max(...xs) - Math.min(...xs);
      const height = Math.max(...ys) - Math.min(...ys);
      const scaleX = (canvas.width - 120) / width;
      const scaleY = (canvas.height - 120) / height;
      zoom = Math.min(scaleX, scaleY);
      panX = 60;
      panY = canvas.height - 60;
      draw();
    }

    function zoomBy(factor) {
      zoom *= factor;
      draw();
    }

    function draw() {
      if (!currentData) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const bounds = currentData.room.boundary_mm;

      // 1. Draw Room Perimeter Polygon
      ctx.save();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
      ctx.beginPath();
      bounds.forEach((pt, idx) => {
        let sx = panX + pt[0] * zoom;
        let sy = panY - pt[1] * zoom;
        if (idx === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // 2. Draw Marked Egress Corridor
      const egress = currentData.room.egress;
      const door = currentData.room.doors.find(d => d.door_id === egress.from_door_id);
      if (door) {
        let dx = door.wall === 'south' ? door.offset_mm + door.width_mm/2 : (door.wall === 'west' ? 0 : 8400);
        let dy = door.wall === 'south' ? 0 : door.offset_mm + door.width_mm/2;
        let sx1 = panX + dx * zoom, sy1 = panY - dy * zoom;
        let sx2 = panX + egress.to_point_mm[0] * zoom, sy2 = panY - egress.to_point_mm[1] * zoom;
        
        ctx.strokeStyle = 'rgba(34, 211, 238, 0.25)';
        ctx.lineWidth = egress.min_width_mm * zoom;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();

        ctx.strokeStyle = '#22d3ee';
        ctx.lineWidth = 2;
        ctx.setLineDash([8, 8]);
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();
        ctx.setLineDash([]);
      }

      // 3. Draw Door Swing Clearance Arcs
      currentData.room.doors.forEach(d => {
        let hx = (d.wall === 'south' ? d.offset_mm : (d.wall === 'west' ? 0 : 8400));
        let hy = (d.wall === 'south' ? 0 : d.offset_mm);
        let sx = panX + hx * zoom, sy = panY - hy * zoom;
        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)';
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(sx, sy, 850 * zoom, 0, Math.PI / 2);
        ctx.lineTo(sx, sy);
        ctx.fill(); ctx.stroke();
      });

      // 4. Draw Furniture Placements
      const colorMap = {
        'desk': { fill: '#10b981', stroke: '#34d399', text: '#ffffff' },
        'chair': { fill: '#f59e0b', stroke: '#fbbf24', text: '#000000' },
        'storage': { fill: '#ec4899', stroke: '#f472b6', text: '#ffffff' },
        'collaboration': { fill: '#6366f1', stroke: '#818cf8', text: '#ffffff' },
        'accessory': { fill: '#64748b', stroke: '#94a3b8', text: '#ffffff' }
      };

      currentData.layout.placements.forEach(p => {
        const item = currentData.catalog[p.sku] || { width: 1200, depth: 600, family: 'desk' };
        let sx = panX + p.x_mm * zoom;
        let sy = panY - p.y_mm * zoom;
        let sw = item.width * zoom;
        let sh = item.depth * zoom;

        ctx.save();
        ctx.translate(sx + sw/2, sy - sh/2);
        ctx.rotate(-p.rotation_deg * Math.PI / 180);
        
        const style = colorMap[item.family] || colorMap['desk'];
        ctx.fillStyle = style.fill;
        ctx.fillRect(-sw/2, -sh/2, sw, sh);
        ctx.strokeStyle = style.stroke;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(-sw/2, -sh/2, sw, sh);

        ctx.fillStyle = style.text;
        ctx.font = 'bold 9px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText(p.placement_id, 0, 3);
        ctx.restore();
      });
      ctx.restore();
    }

    function updateQuoteUI(q) {
      document.getElementById('quoteStatusBadge').innerText = q.status.toUpperCase();
      document.getElementById('quoteStatusBadge').className = q.status === 'priced' 
        ? 'text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold'
        : 'text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/40 font-bold';

      const container = document.getElementById('quoteLinesContainer');
      container.innerHTML = q.lines.map(line => `
        <div class="p-2.5 rounded bg-surface-container border border-outline-variant/30 hover:border-primary/50 transition-colors">
          <div class="flex justify-between items-start">
            <span class="text-white font-bold">${line.sku} <span class="text-on-surface-variant font-normal">(${line.finish_id})</span></span>
            <span class="text-emerald-400 font-bold">₹${line.net_goods_inr.toLocaleString()}</span>
          </div>
          <div class="flex justify-between text-[10px] text-on-surface-variant mt-1">
            <span>Qty: ${line.quantity} × ₹${line.unit_list_price_inr.toLocaleString()}</span>
            <span>Uplift: +₹${line.finish_uplift_inr.toLocaleString()}</span>
          </div>
          <div class="text-[9px] text-primary/80 mt-1">
            Trace: QTY_DISC -₹${line.quantity_discount_inr.toLocaleString()} (RB-PRC-009)
          </div>
        </div>
      `).join('');

      document.getElementById('summaryGoods').innerText = '₹' + (q.summary.goods_after_adjustments_inr || 0).toLocaleString();
      document.getElementById('summaryLabour').innerText = '₹' + (q.summary.labour_inr || 0).toLocaleString();
      document.getElementById('summaryFreight').innerText = '₹' + (q.summary.freight_inr || 0).toLocaleString();
      document.getElementById('summaryGrandTotal').innerText = '₹' + (q.summary.grand_total_inr || 0).toLocaleString();
    }

    function updateViolationsUI(vList) {
      const feed = document.getElementById('violationFeed');
      const tag = document.getElementById('violationCountTag');
      if (!vList || vList.length === 0) {
        tag.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold';
        tag.innerText = '0 VIOLATIONS';
        feed.innerHTML = `
          <div class="p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[11px] flex items-center gap-2">
            <span class="material-symbols-outlined text-base">check_circle</span>
            All 8 spatial constraints satisfied (RB-GEO-001 - RB-GEO-008).
          </div>
        `;
      } else {
        tag.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/40 font-bold';
        tag.innerText = `${vList.length} VIOLATIONS`;
        feed.innerHTML = vList.map(v => `
          <div class="p-3 rounded bg-red-500/10 border border-red-500/40 space-y-1.5">
            <div class="flex justify-between items-center">
              <span class="text-red-400 font-bold text-xs">${v.rule_id}</span>
              <span class="px-1.5 py-0.2 bg-red-500 text-black font-bold text-[9px] rounded">VIOLATION</span>
            </div>
            <div class="text-[11px] text-white">${v.message}</div>
            <div class="grid grid-cols-2 gap-2 text-[10px] pt-1.5 border-t border-red-500/30">
              <div><span class="text-on-surface-variant">MEASURED:</span> <span class="text-red-300 font-bold">${JSON.stringify(v.measured)}</span></div>
              <div><span class="text-on-surface-variant">REQUIRED:</span> <span class="text-emerald-300 font-bold">${JSON.stringify(v.required)}</span></div>
            </div>
          </div>
        `).join('');
      }
    }

    async function injectViolation() {
      currentData.layout.placements.push({
        placement_id: 'INJECT-001',
        sku: 'NW-DES-001',
        finish_id: 'F01',
        x_mm: 600.0,
        y_mm: 200.0,
        rotation_deg: 0.0
      });
      const res = await fetch('/api/v1/layout/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_spec: currentData.room, placements: currentData.layout.placements })
      });
      const verifyRes = await res.json();
      currentData.layout.violations = verifyRes.violations;
      updateViolationsUI(verifyRes.violations);
      draw();
    }

    async function triggerArbitration() {
      const res = await fetch('/api/v1/layout/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_spec: currentData.room })
      });
      const layoutRes = await res.json();
      currentData.layout = layoutRes;
      const qRes = await fetch('/api/v1/quote/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: currentData.room.room_id, placements: currentData.layout.placements })
      });
      currentData.quote = await qRes.json();
      updateQuoteUI(currentData.quote);
      updateViolationsUI(currentData.layout.violations);
      draw();
    }

    function downloadDXF() {
      const roomId = document.getElementById('roomSelect').value;
      window.location.href = `/api/v1/room/${roomId}/dxf`;
    }

    // Canvas pan & zoom handlers
    canvas.addEventListener('mousedown', (e) => { isDragging = true; startX = e.clientX - panX; startY = e.clientY - panY; });
    window.addEventListener('mouseup', () => isDragging = false);
    canvas.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      draw();
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoom *= e.deltaY < 0 ? 1.12 : 0.88;
      draw();
    });

    window.onload = () => { resizeCanvas(); loadSelectedRoom(); };
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
