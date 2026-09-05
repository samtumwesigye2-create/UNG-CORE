from app.services.command_history import serialize_command


def test_command_contract_shape():
    class Row:
        command_id = "cmd-1"
        actor_id = "operator-1"
        command = "alert.acknowledge"
        target_type = "alert"
        target_id = "alert-1"
        system_key = "UNG-NEMSIS"
        correlation_id = "corr-1"
        status = "succeeded"
        result_code = 200
        request_json = "{}"
        before_json = "{}"
        after_json = "{}"
        result_json = "{}"
        requested_at = None
        completed_at = None

    payload = serialize_command(Row())
    assert payload["command_id"] == "cmd-1"
    assert payload["actor_id"] == "operator-1"
    assert payload["system_key"] == "UNG-NEMSIS"
    assert payload["status"] == "succeeded"
    assert payload["correlation_id"] == "corr-1"


def test_command_contract_exposes_change_context():
    class Row:
        command_id = "cmd-2"
        actor_id = "operator-2"
        command = "config.rollback"
        target_type = "configuration"
        target_id = "routing/default"
        system_key = "UNG-CORE"
        correlation_id = None
        status = "accepted"
        result_code = None
        request_json = '{"version":2}'
        before_json = '{"version":3}'
        after_json = '{"version":2}'
        result_json = "{}"
        requested_at = None
        completed_at = None

    payload = serialize_command(Row())
    assert payload["request"]["version"] == 2
    assert payload["before"]["version"] == 3
    assert payload["after"]["version"] == 2
