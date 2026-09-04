"""
Reproducibility manifest: hashed inputs, code, asset pack, and outputs.

Designed so a reviewer can re-run the pipeline and compare SHA-256 digests
without opening every individual evidence JSON file.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "RuleBound_Round1_Release" / "data"
RULES_PATH = DATA_DIR / "rules.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_tree(path: Path) -> str:
    """Stable SHA-256 over relative paths + file bytes (sorted)."""
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        return h.hexdigest()
    files = sorted(p for p in path.rglob("*") if p.is_file())
    for f in files:
        rel = f.relative_to(path).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def git_commit(repo: Path = ROOT) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        sha = (res.stdout or "").strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def output_file_hashes(out_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not out_dir.exists():
        return hashes
    for room_dir in sorted(p for p in out_dir.iterdir() if p.is_dir() and p.name.startswith("ROOM-")):
        for f in sorted(p for p in room_dir.iterdir() if p.is_file()):
            hashes[f"{room_dir.name}/{f.name}"] = sha256_file(f)
    return hashes


def output_manifest_payload(out_dir: Path) -> dict[str, str]:
    return output_file_hashes(out_dir)


def output_manifest_sha256(out_dir: Path) -> str:
    payload = json.dumps(output_manifest_payload(out_dir), sort_keys=True, indent=2) + "\n"
    return sha256_bytes(payload.encode("utf-8"))


def source_tree_sha256(repo: Path = ROOT) -> str:
    """Hash of the deterministic engine sources (not generated OUTPUT/)."""
    h = hashlib.sha256()
    roots = [
        repo / "rulebound",
        repo / "runner.py",
        repo / "judge.py",
        repo / "demo.py",
        repo / "adversarial_test.py",
    ]
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files.extend(p for p in r.rglob("*") if p.is_file() and p.suffix in {".py", ".html", ".bicep"})
    for f in sorted(files, key=lambda p: p.as_posix().lower()):
        rel = f.relative_to(repo).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def build_reproducibility_manifest(
    out_dir: Path | None = None,
    tests_passed: int = 0,
    tests_collected: int | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or (ROOT / "OUTPUT")
    hashes = output_file_hashes(out_dir)
    manifest = {
        "git_commit": git_commit(),
        "python_version": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "asset_pack_sha256": sha256_tree(DATA_DIR),
        "rules_sha256": sha256_file(RULES_PATH) if RULES_PATH.exists() else "",
        "code_sha256": source_tree_sha256(),
        "output_manifest_sha256": output_manifest_sha256(out_dir),
        "output_artifact_count": len(hashes),
        "output_artifacts": hashes,
        "tests_passed": int(tests_passed),
        "tests_collected": tests_collected,
        "chain": [
            {"stage": "Input SHA", "digest": sha256_tree(DATA_DIR), "label": "Asset pack + briefs + rooms"},
            {"stage": "Code SHA", "digest": source_tree_sha256(), "label": "Engine sources (rulebound/, runner, judge)"},
            {"stage": "Asset Pack SHA", "digest": sha256_tree(DATA_DIR), "label": "Released catalog, rules, finishes"},
            {"stage": "Execution", "digest": git_commit(), "label": f"git {git_commit()[:12]} · Python {sys.version.split()[0]}"},
            {"stage": "Output SHA", "digest": output_manifest_sha256(out_dir), "label": f"{len(hashes)} hashed artifacts"},
        ],
    }
    return manifest


def render_reproducibility_ascii(manifest: dict[str, Any]) -> str:
    lines = [
        "REPRODUCIBILITY",
        f"Input SHA        {manifest['asset_pack_sha256'][:16]}…",
        "       ↓",
        f"Code SHA         {manifest['code_sha256'][:16]}…",
        "       ↓",
        f"Asset Pack SHA   {manifest['asset_pack_sha256'][:16]}…",
        "       ↓",
        f"Execution        {manifest['git_commit'][:12]} · {manifest['python_version']}",
        "       ↓",
        f"Output SHA       {manifest['output_manifest_sha256'][:16]}…",
    ]
    return "\n".join(lines)
