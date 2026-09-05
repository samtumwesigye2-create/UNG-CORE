from app.schemas.contracts import AuditEventIn, Principal, RelayEnvelope


def test_principal_contract():
    p = Principal(subject="user-1", roles=["admin"], permissions=["ung.core.admin"])
    assert p.subject == "user-1"
    assert "ung.core.admin" in p.permissions


def test_relay_contract():
    e = RelayEnvelope(event_type="core.test", subject="test", data={"ok": True})
    assert e.source == "UNG-CORE"
    assert e.event_type == "core.test"


def test_audit_contract_defaults_payload():
    event = AuditEventIn(actor_id="user-1", action="read", resource_type="record")
    assert event.payload == {}
