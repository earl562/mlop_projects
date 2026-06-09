"""Tests for Permission System (AC-3.2)."""

from dataclasses import dataclass


class PermissionMode:
    PLAN = "PLAN"
    BUILD = "BUILD"
    AUTO = "AUTO"


class PermissionSystem:
    def __init__(self):
        self.mode = PermissionMode.PLAN

    def set_mode(self, mode: str):
        self.mode = mode

    def can_execute(self, action_type: str) -> tuple[bool, str]:
        if self.mode == PermissionMode.PLAN:
            if action_type in ["send_email", "make_call", "update_crm"]:
                return False, f"PLAN mode blocks external writes: {action_type}"
            return True, "Read operations allowed in PLAN"
        elif self.mode == PermissionMode.BUILD:
            if action_type in ["send_email", "make_call"]:
                return False, "BUILD mode requires approval for external actions"
            return True, "Deterministic operations allowed"
        elif self.mode == PermissionMode.AUTO:
            return True, "AUTO mode allows deterministic operations"
        return False, "Unknown mode"


class TestPermissionSystem:
    def test_plan_mode_blocks_external_writes(self):
        perms = PermissionSystem()
        perms.set_mode(PermissionMode.PLAN)
        allowed, reason = perms.can_execute("send_email")
        assert allowed is False
        assert "PLAN mode" in reason

    def test_plan_mode_allows_reads(self):
        perms = PermissionSystem()
        perms.set_mode(PermissionMode.PLAN)
        allowed, _ = perms.can_execute("search_properties")
        assert allowed is True

    def test_build_mode_blocks_external_actions(self):
        perms = PermissionSystem()
        perms.set_mode(PermissionMode.BUILD)
        allowed, reason = perms.can_execute("make_call")
        assert allowed is False
        assert "approval" in reason

    def test_auto_mode_allows_deterministic(self):
        perms = PermissionSystem()
        perms.set_mode(PermissionMode.AUTO)
        allowed, _ = perms.can_execute("calculate_max_units")
        assert allowed is True
