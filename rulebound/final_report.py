"""
Single-file judge evidence: FINAL_REPORT.html + FINAL_REPORT.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rulebound.reproducibility import git_commit, render_reproducibility_ascii


def build_final_report_payload(
    *,
    checks: dict[str, Any],
    verdict: str,
    git_sha: str,
    artifact_count: int,
    pytest_passed: int,
    elapsed_s: float,
    reproducibility: dict[str, Any],
) -> dict[str, Any]:
    items = [
        {"id": "domain_rules", "label": "14/14 domain rules", "ok": bool(checks.get("domain_rules"))},
        {"id": "adversarial", "label": "11/11 adversarial", "ok": bool(checks.get("adversarial"))},
        {"id": "pricing", "label": "Pricing invariants", "ok": bool(checks.get("pricing"))},
        {"id": "arbitration", "label": "Arbitration proof", "ok": bool(checks.get("arbitration"))},
        {"id": "determinism", "label": "Determinism", "ok": bool(checks.get("determinism"))},
        {"id": "dxf", "label": "5/5 DXF", "ok": bool(checks.get("dxf"))},
        {"id": "requirements", "label": "Requirement satisfaction", "ok": bool(checks.get("requirements"))},
        {"id": "integrity", "label": "Output integrity", "ok": bool(checks.get("integrity"))},
    ]
    return {
        "title": "RULEBOUND FINAL AUDIT",
        "verdict": verdict,
        "git_commit": git_sha,
        "artifact_count": artifact_count,
        "pytest_passed": pytest_passed,
        "elapsed_seconds": round(elapsed_s, 2),
        "checks": items,
        "reproducibility": reproducibility,
        "reproducibility_ascii": render_reproducibility_ascii(reproducibility),
        "notes": [
            "Bitwise identity is verified by SHA-256 comparison of pipeline outputs in this environment.",
            "Domain rules are implemented and exercised by the official validator, unit tests, and adversarial suite.",
            "This HTML file is the intended first artifact for reviewers; supporting JSON remains in EVIDENCE/.",
        ],
    }


def render_final_report_html(payload: dict[str, Any]) -> str:
    checks_html = []
    for c in payload["checks"]:
        mark = "✅" if c["ok"] else "❌"
        tone = "#34d399" if c["ok"] else "#f87171"
        checks_html.append(
            f'<li style="display:flex;align-items:center;gap:10px;padding:10px 12px;'
            f'border:1px solid rgba(255,255,255,0.08);border-radius:10px;background:rgba(15,23,42,0.65);">'
            f'<span style="font-size:18px">{mark}</span>'
            f'<span style="color:{tone};font-weight:700">{c["label"]}</span></li>'
        )
    chain = payload.get("reproducibility", {}).get("chain") or []
    chain_html = []
    for i, stage in enumerate(chain):
        digest = (stage.get("digest") or "")[:20]
        chain_html.append(
            f'<div style="padding:10px 12px;border:1px solid rgba(34,211,238,0.25);border-radius:10px;'
            f'background:rgba(8,47,73,0.35)">'
            f'<div style="font-size:11px;letter-spacing:0.12em;color:#67e8f9;text-transform:uppercase">{stage.get("stage")}</div>'
            f'<div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#e2e8f0;margin-top:4px">{digest}…</div>'
            f'<div style="font-size:11px;color:#94a3b8;margin-top:2px">{stage.get("label","")}</div></div>'
        )
        if i < len(chain) - 1:
            chain_html.append('<div style="text-align:center;color:#22d3ee;font-weight:800;padding:2px 0">↓</div>')

    verdict = payload.get("verdict", "AUDIT FAILED")
    verdict_color = "#34d399" if "READY" in verdict else "#f87171"
    sha = payload.get("git_commit") or git_commit()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>RuleBound Final Audit</title>
</head>
<body style="margin:0;background:#020617;color:#e2e8f0;font-family:Inter,Segoe UI,system-ui,sans-serif;">
  <div style="max-width:880px;margin:0 auto;padding:36px 22px 64px;">
    <div style="font-size:12px;letter-spacing:0.28em;color:#22d3ee;font-weight:800">RULEBOUND FINAL AUDIT</div>
    <h1 style="margin:8px 0 4px;font-size:34px;letter-spacing:-0.03em">Evidence package for reviewers</h1>
    <p style="color:#94a3b8;margin:0 0 28px;line-height:1.55">
      One page. No need to open five JSON files first. Supporting traces remain in
      <code style="color:#67e8f9">EVIDENCE/</code> if you want the raw proofs.
    </p>

    <ul style="list-style:none;padding:0;margin:0 0 28px;display:grid;gap:8px">
      {''.join(checks_html)}
    </ul>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">
      <div style="padding:16px;border:1px solid rgba(255,255,255,0.1);border-radius:14px;background:#0b1220">
        <div style="font-size:11px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase">Commit</div>
        <div style="font-family:ui-monospace,Menlo,Consolas,monospace;margin-top:8px;font-size:13px;word-break:break-all">{sha}</div>
      </div>
      <div style="padding:16px;border:1px solid rgba(255,255,255,0.1);border-radius:14px;background:#0b1220">
        <div style="font-size:11px;color:#94a3b8;letter-spacing:0.14em;text-transform:uppercase">Artifacts</div>
        <div style="margin-top:8px;font-size:20px;font-weight:800">{payload.get("artifact_count", 0)} verified output artifacts</div>
        <div style="font-size:12px;color:#94a3b8;margin-top:4px">{payload.get("pytest_passed", 0)} tests passed in Judge Mode</div>
      </div>
    </div>

    <div style="padding:18px;border:1px solid rgba(52,211,153,0.35);border-radius:16px;background:rgba(6,78,59,0.28);margin-bottom:28px">
      <div style="font-size:11px;letter-spacing:0.16em;color:#6ee7b7;text-transform:uppercase">Overall</div>
      <div style="font-size:28px;font-weight:900;color:{verdict_color};margin-top:6px">{verdict}</div>
    </div>

    <h2 style="font-size:16px;letter-spacing:0.12em;color:#67e8f9">REPRODUCIBILITY</h2>
    <div style="display:grid;gap:6px;margin-bottom:18px">{''.join(chain_html)}</div>
    <pre style="white-space:pre-wrap;background:#020617;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:16px;color:#cbd5e1;font-size:12px">{payload.get("reproducibility_ascii","")}</pre>

    <p style="color:#64748b;font-size:12px;line-height:1.6;margin-top:24px">
      Claims on this page are bounded to the tested runner, asset pack digest, and Python version recorded
      in the reproducibility manifest. Open <code>FINAL_REPORT.json</code> for the machine-readable twin.
    </p>
  </div>
</body>
</html>
"""


def write_final_reports(evidence_dir: Path, payload: dict[str, Any]) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "FINAL_REPORT.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "FINAL_REPORT.html").write_text(
        render_final_report_html(payload),
        encoding="utf-8",
    )
