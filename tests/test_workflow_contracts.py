from app.schemas.workflows import WorkflowStartIn


def test_workflow_start_contract():
    body = WorkflowStartIn(
        workflow_key="national-emergency-coordination",
        subject="UNG-NEMSIS:incident-001",
        input={"severity": "critical"},
    )
    assert body.workflow_key == "national-emergency-coordination"
    assert body.input["severity"] == "critical"
