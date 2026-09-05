from app.schemas.contracts import Principal, RelayEnvelope

def test_principal_contract():
    p = Principal(subject="user-1", roles=["admin"], permissions=["core.read"])
    assert p.subject == "user-1"

def test_relay_contract():
    e = RelayEnvelope(event_type="core.test", subject="test", data={"ok": True})
    assert e.source == "UNG-CORE"
