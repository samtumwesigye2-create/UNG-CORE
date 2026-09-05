from app.schemas.registry import ServiceRegistrationIn


def test_service_registration_contract():
    service = ServiceRegistrationIn(
        service_key="UNG-IAM",
        display_name="UNG Identity and Access Management",
        base_url="https://iam.example.test",
        version="1.0.0",
        capabilities=["identity", "authentication", "authorization"],
    )
    assert service.service_key == "UNG-IAM"
    assert "authorization" in service.capabilities


def test_registry_health_path_default():
    service = ServiceRegistrationIn(
        service_key="UNG-MDM",
        display_name="UNG Master Data Management",
        base_url="https://mdm.example.test",
    )
    assert service.health_path == "/health"
