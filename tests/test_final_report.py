from pathlib import Path

from rulebound.final_report import build_final_report_payload, render_final_report_html
from rulebound.reproducibility import build_reproducibility_manifest, render_reproducibility_ascii

ROOT = Path(__file__).resolve().parents[1]


def test_reproducibility_manifest_fields():
    man = build_reproducibility_manifest(ROOT / "OUTPUT", tests_passed=0)
    for key in (
        "git_commit",
        "python_version",
        "platform",
        "asset_pack_sha256",
        "rules_sha256",
        "output_manifest_sha256",
        "tests_passed",
        "code_sha256",
    ):
        assert key in man
    assert len(man["asset_pack_sha256"]) == 64
    assert len(man["rules_sha256"]) == 64
    ascii_card = render_reproducibility_ascii(man)
    assert "REPRODUCIBILITY" in ascii_card
    assert "Input SHA" in ascii_card
    assert "Code SHA" in ascii_card
    assert "Output SHA" in ascii_card


def test_final_report_html_contains_reviewer_card():
    man = build_reproducibility_manifest(ROOT / "OUTPUT", tests_passed=12)
    payload = build_final_report_payload(
        checks={
            "domain_rules": True,
            "adversarial": True,
            "pricing": True,
            "arbitration": True,
            "determinism": True,
            "dxf": True,
            "requirements": True,
            "integrity": True,
        },
        verdict="SUBMISSION READY",
        git_sha=man["git_commit"],
        artifact_count=15,
        pytest_passed=12,
        elapsed_s=1.0,
        reproducibility=man,
    )
    html = render_final_report_html(payload)
    assert "RULEBOUND FINAL AUDIT" in html
    assert "14/14 domain rules" in html
    assert "11/11 adversarial" in html
    assert "SUBMISSION READY" in html
    assert "15 verified output artifacts" in html
    assert man["git_commit"][:8] in html or man["git_commit"] in html
