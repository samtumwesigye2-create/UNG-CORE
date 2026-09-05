from app.schemas.incidents import IncidentSummaryOut


def test_incident_summary_contract():
    summary = IncidentSummaryOut(open_total=2, critical=1, warning=1, resolved_total=4, affected_services=["UNG-IAM", "UNG-NEMSIS"])
    assert summary.open_total == 2
    assert "UNG-NEMSIS" in summary.affected_services
