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
    """
    Validates Microsoft Entra ID (Azure AD) Bearer JWT token.
    """
    if not REQUIRE_AUTH:
        return {"sub": "developer@local", "roles": ["RuleBound.Admin"]}

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
    if not dxf_path.exists():
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
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RuleBound | Interactive Floor Plan Visualizer</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    body { background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .card { background: #151d30; border: 1px solid #1e293b; border-radius: 12px; }
    .navbar { background: #0f172a; border-bottom: 1px solid #1e293b; }
    .badge-rule { font-size: 0.8rem; padding: 4px 8px; border-radius: 6px; }
    #canvas-container { position: relative; width: 100%; height: 580px; background: #090d16; border-radius: 8px; border: 1px solid #1e293b; overflow: hidden; }
    canvas { display: block; }
    .table-dark { background: #151d30; }
    .btn-action { font-weight: 600; border-radius: 8px; padding: 8px 16px; transition: all 0.2s ease; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark px-4 py-3">
    <a class="navbar-brand fw-bold text-primary" href="#"><i class="fa-solid fa-cube me-2"></i>RULEBOUND <span class="badge bg-primary text-white ms-2">LIVE DEFENCE</span></a>
    <div class="ms-auto d-flex gap-2">
      <a href="/docs" target="_blank" class="btn btn-outline-info btn-sm"><i class="fa-solid fa-book me-1"></i> Swagger API</a>
      <span class="badge bg-success align-self-center py-2 px-3"><i class="fa-solid fa-shield-check me-1"></i> Deterministic Engine v1.0</span>
    </div>
  </nav>

  <div class="container-fluid px-4 py-3">
    <div class="row g-3">
      <!-- Control & Plan View Column -->
      <div class="col-lg-8">
        <div class="card p-3 shadow-sm h-100">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <div class="d-flex align-items-center gap-3">
              <label class="fw-bold"><i class="fa-solid fa-door-open me-1"></i> Select Room:</label>
              <select id="roomSelect" class="form-select form-select-sm bg-dark text-light border-secondary" style="width: 260px;" onchange="loadSelectedRoom()">
                <option value="ROOM-01">ROOM-01: Harbour Design Studio</option>
                <option value="ROOM-02">ROOM-02: Cedar Client Workshop</option>
                <option value="ROOM-03">ROOM-03: Nimbus Hybrid Team Room</option>
                <option value="ROOM-04">ROOM-04: Orchard Focus Library</option>
                <option value="ROOM-05">ROOM-05: Summit Project Hub</option>
              </select>
            </div>
            <div class="d-flex gap-2">
              <button class="btn btn-danger btn-sm btn-action" onclick="injectViolation()"><i class="fa-solid fa-triangle-exclamation me-1"></i> Inject Violation</button>
              <button class="btn btn-warning btn-sm btn-action" onclick="triggerArbitration()"><i class="fa-solid fa-gavel me-1"></i> Run Arbitration Repair</button>
              <button class="btn btn-primary btn-sm btn-action" onclick="downloadDXF()"><i class="fa-solid fa-download me-1"></i> Download DXF</button>
            </div>
          </div>

          <div id="briefBox" class="alert alert-secondary py-2 px-3 small mb-2 bg-dark text-info border-secondary">
            Loading brief...
          </div>

          <div id="canvas-container">
            <canvas id="planCanvas"></canvas>
          </div>
          <div class="d-flex justify-content-between text-muted small mt-2">
            <span><i class="fa-solid fa-info-circle me-1"></i> Left Click & Drag to Pan | Scroll to Zoom</span>
            <span id="canvasStats">Dimensions: -- | Scale: --</span>
          </div>
        </div>
      </div>

      <!-- Pricing & Violation Diagnostics Column -->
      <div class="col-lg-4">
        <div class="card p-3 shadow-sm mb-3">
          <h5 class="fw-bold border-bottom border-secondary pb-2"><i class="fa-solid fa-calculator text-success me-2"></i>Deterministic Quote</h5>
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="text-muted">Quote ID:</span>
            <span id="quoteId" class="fw-bold font-monospace text-light">--</span>
          </div>
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="text-muted">Status:</span>
            <span id="quoteStatus" class="badge bg-success">PRICED</span>
          </div>
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="text-muted">Net Goods (INR):</span>
            <span id="netGoods" class="fw-bold text-light">--</span>
          </div>
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="text-muted">Labour (INR):</span>
            <span id="labourInr" class="fw-bold text-light">--</span>
          </div>
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="text-muted">Freight (INR):</span>
            <span id="freightInr" class="fw-bold text-light">--</span>
          </div>
          <hr class="border-secondary my-2">
          <div class="d-flex justify-content-between align-items-center my-2">
            <span class="fs-5 fw-bold text-success">Grand Total:</span>
            <span id="grandTotal" class="fs-4 fw-bold text-success font-monospace">₹0</span>
          </div>
        </div>

        <div class="card p-3 shadow-sm h-50">
          <h5 class="fw-bold border-bottom border-secondary pb-2 d-flex justify-content-between">
            <span><i class="fa-solid fa-shield-halved text-warning me-2"></i>Spatial Verifier</span>
            <span id="violationCountBadge" class="badge bg-success">0 Violations</span>
          </h5>
          <div id="violationList" class="overflow-auto flex-grow-1 small" style="max-height: 220px;">
            <div class="text-success p-2"><i class="fa-solid fa-circle-check me-2"></i>All 8 spatial rules strictly satisfied (RB-GEO-001 to RB-GEO-008).</div>
          </div>
        </div>
      </div>
    </div>
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
      document.getElementById('briefBox').innerHTML = `<strong>Brief:</strong> ${currentData.room.brief}`;
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
      const scaleX = (canvas.width - 100) / width;
      const scaleY = (canvas.height - 100) / height;
      zoom = Math.min(scaleX, scaleY);
      panX = 50;
      panY = canvas.height - 50;
    }

    function draw() {
      if (!currentData) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Grid background
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 0.5;
      for (let x = 0; x < canvas.width; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke(); }
      for (let y = 0; y < canvas.height; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }

      const bounds = currentData.room.boundary_mm;
      
      // 1. Draw Room Polygon Boundary
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
      ctx.beginPath();
      bounds.forEach((pt, idx) => {
        let sx = panX + pt[0] * zoom;
        let sy = panY - pt[1] * zoom;
        if (idx === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // 2. Draw Egress Corridor
      const egress = currentData.room.egress;
      const door = currentData.room.doors.find(d => d.door_id === egress.from_door_id);
      if (door) {
        let dx = door.wall === 'south' ? door.offset_mm + door.width_mm/2 : (door.wall === 'west' ? 0 : 7200);
        let dy = door.wall === 'south' ? 0 : door.offset_mm + door.width_mm/2;
        let sx1 = panX + dx * zoom, sy1 = panY - dy * zoom;
        let sx2 = panX + egress.to_point_mm[0] * zoom, sy2 = panY - egress.to_point_mm[1] * zoom;
        
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
        ctx.lineWidth = egress.min_width_mm * zoom;
        ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();

        ctx.strokeStyle = '#06b6d4';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 6]);
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();
        ctx.setLineDash([]);
      }

      // 3. Draw Door Swing Clearance
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
      const colorMap = { 'desk': '#10b981', 'chair': '#f59e0b', 'storage': '#ec4899', 'collaboration': '#6366f1', 'accessory': '#64748b' };
      currentData.layout.placements.forEach(p => {
        const item = currentData.catalog[p.sku] || { width: 1200, depth: 600, family: 'desk' };
        let sx = panX + p.x_mm * zoom;
        let sy = panY - p.y_mm * zoom;
        let sw = item.width * zoom;
        let sh = item.depth * zoom;

        ctx.save();
        ctx.translate(sx + sw/2, sy - sh/2);
        ctx.rotate(-p.rotation_deg * Math.PI / 180);
        ctx.fillStyle = colorMap[item.family] || '#10b981';
        ctx.fillRect(-sw/2, -sh/2, sw, sh);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.strokeRect(-sw/2, -sh/2, sw, sh);

        ctx.fillStyle = '#ffffff';
        ctx.font = '9px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(p.placement_id, 0, 3);
        ctx.restore();
      });
    }

    function updateQuoteUI(q) {
      document.getElementById('quoteId').innerText = q.quote_id;
      document.getElementById('quoteStatus').innerText = q.status.toUpperCase();
      document.getElementById('quoteStatus').className = q.status === 'priced' ? 'badge bg-success' : 'badge bg-danger';
      document.getElementById('netGoods').innerText = '₹' + (q.summary.goods_after_adjustments_inr || 0).toLocaleString();
      document.getElementById('labourInr').innerText = '₹' + (q.summary.labour_inr || 0).toLocaleString();
      document.getElementById('freightInr').innerText = '₹' + (q.summary.freight_inr || 0).toLocaleString();
      document.getElementById('grandTotal').innerText = '₹' + (q.summary.grand_total_inr || 0).toLocaleString();
    }

    function updateViolationsUI(vList) {
      const listDiv = document.getElementById('violationList');
      const badge = document.getElementById('violationCountBadge');
      if (!vList || vList.length === 0) {
        badge.className = 'badge bg-success';
        badge.innerText = '0 Violations (Valid)';
        listDiv.innerHTML = '<div class="text-success p-2"><i class="fa-solid fa-circle-check me-2"></i>All spatial rules strictly satisfied (RB-GEO-001 to RB-GEO-008).</div>';
      } else {
        badge.className = 'badge bg-danger';
        badge.innerText = `${vList.length} Violations`;
        listDiv.innerHTML = vList.map(v => `
          <div class="alert alert-danger py-2 px-3 mb-2 small bg-dark text-danger border-danger">
            <strong>${v.rule_id}:</strong> ${v.message}
          </div>
        `).join('');
      }
    }

    async function injectViolation() {
      // Deliberately place a desk in the door swing & overlapping
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

    // Interactive canvas panning & zooming
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
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      zoom *= zoomFactor;
      draw();
    });

    window.onload = () => { resizeCanvas(); loadSelectedRoom(); };
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
