from app.schemas.control_plane import ConfigurationIn, DependencyIn, OrganizationIn, SystemIn


def test_organization_contract():
    body = OrganizationIn(organization_key="UNG", display_name="Uganda National Grid")
    assert body.enabled is True


def test_system_contract_uses_independent_system_identity():
    body = SystemIn(
        system_key="UNG-NEMSIS",
        display_name="National Emergency Management Services Information System",
        owner_organization_key="UNG",
        criticality="national-critical",
        capabilities=["incident-management", "emergency-coordination"],
    )
    assert body.system_key == "UNG-NEMSIS"
    assert "emergency-coordination" in body.capabilities


def test_dependency_contract():
    dependency = DependencyIn(depends_on_system_key="UNG-IAM", dependency_type="identity")
    assert dependency.required is True


def test_configuration_contract_supports_secret_reference():
    config = ConfigurationIn(value="secret://ung-core/relay-token", is_secret_reference=True)
    assert config.is_secret_reference is True
