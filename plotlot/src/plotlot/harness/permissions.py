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
