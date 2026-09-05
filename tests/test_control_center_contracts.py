from app.services.control_plane import serialize_configuration_version


def test_control_center_route_contracts_exist():
    from app.api.control_center_routes import router

    paths = {route.path for route in router.routes}
    assert "/v1/control-center/topology" in paths
    assert "/v1/control-center/config/{scope}/{config_key}/history" in paths
    assert "/v1/control-center/config/{scope}/{config_key}/rollback/{version}" in paths
    assert "/v1/control-center/ui" in paths


def test_configuration_version_serializer_contract():
    class Row:
        scope = "UNG-NEMSIS"
        config_key = "incident.priority.default"
        version = 3
        value_json = '"critical"'
        changed_by = "operator-001"
        changed_at = None

    data = serialize_configuration_version(Row())
    assert data["scope"] == "UNG-NEMSIS"
    assert data["version"] == 3
    assert data["value"] == "critical"
