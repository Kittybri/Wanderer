"""P0 stack rehearsal must keep every sibling preservation suite."""
from pathlib import Path


def test_p0_rehearsal_preservation_union():
    content=(Path(__file__).resolve().parents[1]/".github/workflows/preservation.yml").read_text()
    needed=["test_preservation.py","test_tarot_restoration.py","test_partner_reply_routing.py","test_tarot_quality.py","test_google_production_site.py","test_docfix_safety.py","test_admin_authorization.py","test_provider_status_resilience.py","test_dependency_compatibility.py","test_integration_docs_contract.py"]
    run=next(ln for ln in content.splitlines() if "run: python -m pytest -q" in ln)
    for name in needed:
        assert "tests/"+name in run, name
