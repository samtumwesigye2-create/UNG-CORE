import pytest
from app.services.operator_commands import COMMANDS, CommandError, parse_command
from app.services.unified_operations import (
    InvalidOperation,
    authorize_resource_action,
    evaluate_transition,
    parse_semver,
)


def test_operator_command_parser_accepts_optional_ung_prefix():
    assert parse_command("UNG JOBS") == ("JOBS", [])
    assert parse_command("find vector") == ("FIND", ["vector"])


def test_operator_command_parser_rejects_unknown_command():
    with pytest.raises(CommandError):
        parse_command("UNG DESTROY EVERYTHING")


def test_all_control_plane_commands_are_registered():
    expected = {
        "STATUS", "JOBS", "SERVICES", "REPORTS", "FIND", "SHOW", "LOGS",
        "HEALTH", "EVENTS", "USERS", "SESSIONS", "STORAGE", "DATABASES",
        "QUEUES", "CONNECTIONS", "START", "STOP", "RESTART", "AUDIT", "SIGNOFF",
    }
    assert set(COMMANDS) == expected
    for command in expected:
        parsed, _ = parse_command(f"UNG {command}")
        assert parsed == command


def test_lifecycle_commands_require_exactly_one_resource_argument():
    for command in ("START", "STOP", "RESTART"):
        parsed, args = parse_command(f"UNG {command} service:vector")
        assert parsed == command
        assert args == ["service:vector"]


def test_semver_parser_is_strict():
    assert parse_semver("2.4.1") == (2, 4, 1)
    with pytest.raises(InvalidOperation):
        parse_semver("v2.4")


def test_compatibility_policies():
    assert evaluate_transition("1.2.3", "1.9.0", "major-stable") is True
    assert evaluate_transition("1.2.3", "2.0.0", "major-stable") is False
    assert evaluate_transition("1.2.3", "1.2.9", "minor-stable") is True
    assert evaluate_transition("1.2.3", "1.3.0", "minor-stable") is False
    assert evaluate_transition("1.2.3", "1.2.3", "exact") is True
    assert evaluate_transition("1.2.3", "1.2.4", "exact") is False


def test_compatibility_rejects_downgrades_and_unknown_policy():
    assert evaluate_transition("1.2.3", "1.2.2", "major-stable") is False
    assert evaluate_transition("1.2.3", "1.2.2", "minor-stable") is False
    with pytest.raises(InvalidOperation):
        evaluate_transition("1.2.3", "1.2.4", "anything-goes")


class Principal:
    def __init__(self, permissions):
        self.permissions = permissions
        self.subject = "acceptance-user"


class Resource:
    def __init__(self, controllable=True):
        self.controllable = controllable


def test_service_authorization_requires_action_permission():
    assert authorize_resource_action(
        Principal(["ung.core.services.start"]), Resource(), "start"
    ) is True
    with pytest.raises(PermissionError):
        authorize_resource_action(Principal([]), Resource(), "start")


def test_each_lifecycle_action_has_independent_permission():
    for action in ("start", "stop", "restart"):
        principal = Principal([f"ung.core.services.{action}"])
        assert authorize_resource_action(principal, Resource(), action) is True


def test_core_admin_override_and_non_controllable_guard():
    assert authorize_resource_action(
        Principal(["ung.core.admin"]), Resource(), "restart"
    ) is True
    with pytest.raises(InvalidOperation):
        authorize_resource_action(
            Principal(["ung.core.admin"]), Resource(controllable=False), "stop"
        )


def test_acceptance_matrix_covers_group_two_boundaries():
    # Compatibility, lifecycle authorization, command registration and parser
    # are intentionally tested together as the final regression boundary.
    assert evaluate_transition("3.1.0", "3.2.0", "major-stable") is True
    assert authorize_resource_action(
        Principal(["ung.core.services.restart"]), Resource(), "restart"
    ) is True
    assert parse_command("UNG SIGNOFF") == ("SIGNOFF", [])
