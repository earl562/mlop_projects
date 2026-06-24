from __future__ import annotations

from typing import Final, assert_never

from plotlot.dev.agent_loop_models import CommandSpec, LoopConfig, Phase


PROFILE_PHASES: Final[dict[str, tuple[Phase, ...]]] = {
    "smoke": (Phase.PLAN, Phase.DEBUG, Phase.HYGIENE),
    "backend": (Phase.PLAN, Phase.DEBUG, Phase.HYGIENE, Phase.BACKEND),
    "frontend": (Phase.PLAN, Phase.DEBUG, Phase.FRONTEND, Phase.BROWSER),
    "full": (
        Phase.PLAN,
        Phase.DEBUG,
        Phase.HYGIENE,
        Phase.BACKEND,
        Phase.EVAL,
        Phase.FRONTEND,
        Phase.BROWSER,
        Phase.REVIEW,
    ),
    "deploy-readiness": (
        Phase.PLAN,
        Phase.DEBUG,
        Phase.HYGIENE,
        Phase.EVAL,
        Phase.REVIEW,
        Phase.DEPLOY_READINESS,
    ),
}


def profile_phases(profile: str) -> tuple[Phase, ...]:
    return PROFILE_PHASES[profile]


def build_commands(config: LoopConfig) -> tuple[CommandSpec, ...]:
    commands: list[CommandSpec] = []
    for phase in config.phases:
        commands.extend(_commands_for_phase(phase, config))
    return tuple(commands)


def _commands_for_phase(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    match phase:
        case Phase.PLAN:
            return _plan_commands(phase, config)
        case Phase.DEBUG:
            return _debug_commands(phase, config)
        case Phase.HYGIENE:
            return _hygiene_commands(phase, config)
        case Phase.BACKEND:
            return _backend_commands(phase, config)
        case Phase.EVAL:
            return _eval_commands(phase, config)
        case Phase.FRONTEND:
            return _frontend_commands(phase, config)
        case Phase.BROWSER:
            return _browser_commands(phase, config)
        case Phase.REVIEW:
            return _review_commands(phase, config)
        case Phase.DEPLOY_READINESS:
            return _deploy_readiness_commands(phase, config)
        case unreachable:
            assert_never(unreachable)


def _plan_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "git-status", phase, ("git", "status", "--short", "--branch"), config.repo_root
        ),
        CommandSpec("git-diff-stat", phase, ("git", "diff", "--stat"), config.repo_root),
    )


def _debug_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("python-version", phase, ("python3", "--version"), config.app_root),
        CommandSpec("uv-version", phase, ("uv", "--version"), config.app_root),
        CommandSpec("node-version", phase, ("node", "--version"), config.app_root),
        CommandSpec("npm-version", phase, ("npm", "--version"), config.app_root),
        CommandSpec(
            "auth-readiness",
            phase,
            ("python3", "scripts/check_auth_readiness.py"),
            config.app_root,
            optional=True,
        ),
    )


def _hygiene_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "repo-hygiene",
            phase,
            ("python3", "scripts/check_repo_hygiene.py"),
            config.app_root,
        ),
        CommandSpec(
            "workflow-policy",
            phase,
            ("python3", "scripts/validate_workflows.py"),
            config.app_root,
        ),
    )


def _backend_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "ruff-check",
            phase,
            ("uv", "run", "ruff", "check", "src/", "tests/", "scripts/"),
            config.app_root,
        ),
        CommandSpec(
            "ruff-format-check",
            phase,
            ("uv", "run", "ruff", "format", "--check", "src/", "tests/"),
            config.app_root,
        ),
        CommandSpec("mypy", phase, ("uv", "run", "mypy", "src/plotlot/"), config.app_root),
        CommandSpec(
            "backend-unit-tests",
            phase,
            ("uv", "run", "pytest", "tests/unit/", "-q"),
            config.app_root,
        ),
    )


def _eval_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "lookup-eval-gates",
            phase,
            (
                "uv",
                "run",
                "pytest",
                "tests/eval/test_eval_scorers.py",
                "tests/eval/test_eval_offline.py",
                "tests/eval/test_southfl_golden.py",
                "tests/eval/test_agentic_land_use_goldset.py",
                "-v",
                "--tb=short",
                "--strict-markers",
            ),
            config.app_root,
        ),
    )


def _frontend_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    frontend_root = config.app_root / "frontend"
    return (
        CommandSpec("frontend-lint", phase, ("npm", "run", "lint"), frontend_root),
        CommandSpec("frontend-typecheck", phase, ("npx", "tsc", "--noEmit"), frontend_root),
        CommandSpec("frontend-ui-tests", phase, ("npm", "run", "test:ui"), frontend_root),
        CommandSpec("frontend-build", phase, ("npm", "run", "build"), frontend_root),
    )


def _browser_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "playwright-design-system",
            phase,
            (
                "npx",
                "playwright",
                "test",
                "tests/design-system.spec.ts",
                "--project=chromium",
            ),
            config.app_root / "frontend",
        ),
    )


def _review_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("review-diff-check", phase, ("git", "diff", "--check"), config.repo_root),
        CommandSpec(
            "review-branch-log", phase, ("git", "log", "-5", "--oneline"), config.repo_root
        ),
    )


def _deploy_readiness_commands(phase: Phase, config: LoopConfig) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "gh-auth-status",
            phase,
            ("gh", "auth", "status"),
            config.repo_root,
            optional=True,
        ),
        CommandSpec(
            "gh-pr-status",
            phase,
            ("gh", "pr", "status"),
            config.repo_root,
            optional=True,
        ),
    )
