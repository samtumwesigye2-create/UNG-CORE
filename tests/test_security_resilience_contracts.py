from app.models.security_resilience import CircuitState, DeadLetter, ServiceCredential


def test_service_credential_stores_reference_not_secret_value():
    row = ServiceCredential(credential_key="nemsis-api", system_key="UNG-NEMSIS", secret_env_var="UNG_NEMSIS_API_TOKEN")
    assert row.secret_env_var == "UNG_NEMSIS_API_TOKEN"
    assert not hasattr(row, "secret_value")


def test_circuit_defaults_closed():
    row = CircuitState(system_key="UNG-NEMSIS")
    assert row.state in (None, "closed")
    assert row.failure_threshold in (None, 5)


def test_dead_letter_contract_shape():
    row = DeadLetter(source_type="job", source_id="job-1", action="http.request")
    assert row.source_type == "job"
    assert row.action == "http.request"
    assert hasattr(row, "replay_count")
