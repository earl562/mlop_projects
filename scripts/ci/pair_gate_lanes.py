from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pair_gate_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class Lane:
    identifier: str
    repository: str
    command: list[str]
    cwd: str | None = None
    report: JsonObject | None = None
    browser_artifact: str | None = None
    environment: JsonObject | None = None
    expected_test_count: int | None = None

    def to_json(self) -> JsonObject:
        command_values: list[JsonValue] = [item for item in self.command]
        value: JsonObject = {
            "id": self.identifier,
            "repository": self.repository,
            "command": command_values,
            "timeoutSeconds": 1800,
        }
        if self.cwd is not None:
            value["cwd"] = self.cwd
        if self.report is not None:
            value["report"] = self.report
        if self.browser_artifact is not None:
            value["browserArtifactGlob"] = self.browser_artifact
        if self.environment is not None:
            value["environment"] = self.environment
        if self.expected_test_count is not None:
            value["expectedTestCount"] = self.expected_test_count
        return value


def lanes(artifact_root: Path) -> list[JsonValue]:
    pytest_report = artifact_root / "reports/plotlot-pytest.xml"
    pytest_inventory = artifact_root / "reports/plotlot-pytest-inventory.json"
    frontend_report = artifact_root / "reports/plotlot-vitest.json"
    byright_report = artifact_root / "reports/byright-vitest.json"
    plotlot_browser = artifact_root / "reports/plotlot-playwright.json"
    byright_browser = artifact_root / "reports/byright-playwright.json"
    return [
        value.to_json()
        for value in (
            Lane(
                "plotlot-install",
                "plotlot",
                ["uv", "sync", "--frozen", "--extra", "dev", "--extra", "eval"],
                cwd="plotlot",
            ),
            Lane(
                "plotlot-ruff",
                "plotlot",
                ["uv", "run", "ruff", "check", "src/", "tests/"],
                cwd="plotlot",
            ),
            Lane(
                "plotlot-pytest-inventory",
                "plotlot",
                [
                    "uv",
                    "run",
                    "python",
                    "../scripts/ci/collect_pytest_inventory.py",
                    "--output",
                    str(pytest_inventory),
                ],
                cwd="plotlot",
                report={
                    "format": "collection",
                    "path": "reports/plotlot-pytest-inventory.json",
                },
            ),
            Lane(
                "plotlot-mypy",
                "plotlot",
                ["uv", "run", "mypy", "src/plotlot/", "--no-error-summary"],
                cwd="plotlot",
            ),
            Lane(
                "plotlot-pytest",
                "plotlot",
                [
                    "uv",
                    "run",
                    "pytest",
                    "tests/architecture/",
                    "tests/contracts/",
                    "tests/eval/",
                    "--ignore=tests/eval/test_eval_live.py",
                    "--ignore=tests/eval/test_ingestion_golden_queries.py",
                    "tests/unit/",
                    "tests/security/",
                    "-q",
                    f"--junitxml={pytest_report}",
                ],
                cwd="plotlot",
                report={"format": "junit", "path": "reports/plotlot-pytest.xml"},
            ),
            Lane("plotlot-build", "plotlot", ["uv", "build"], cwd="plotlot"),
            Lane("plotlot-frontend-install", "plotlot", ["npm", "ci"], cwd="plotlot/frontend"),
            Lane(
                "plotlot-playwright-install",
                "plotlot",
                ["npx", "playwright", "install", "chromium"],
                cwd="plotlot/frontend",
            ),
            Lane(
                "plotlot-frontend-lint", "plotlot", ["npm", "run", "lint"], cwd="plotlot/frontend"
            ),
            Lane(
                "plotlot-frontend-typecheck",
                "plotlot",
                ["npx", "tsc", "--noEmit"],
                cwd="plotlot/frontend",
            ),
            Lane(
                "plotlot-frontend-vitest",
                "plotlot",
                [
                    "npx",
                    "vitest",
                    "run",
                    "--config",
                    "vitest.config.ts",
                    "--reporter=json",
                    f"--outputFile={frontend_report}",
                ],
                cwd="plotlot/frontend",
                report={"format": "vitest", "path": "reports/plotlot-vitest.json"},
            ),
            Lane(
                "plotlot-frontend-build", "plotlot", ["npm", "run", "build"], cwd="plotlot/frontend"
            ),
            Lane(
                "plotlot-frontend-auth-boundary",
                "plotlot",
                ["python3", "../../scripts/ci/verify_frontend_auth_boundary.py"],
                cwd="plotlot/frontend",
            ),
            Lane(
                "plotlot-playwright",
                "plotlot",
                ["python3", "../../scripts/ci/run_plotlot_playwright.py"],
                cwd="plotlot/frontend",
                report={"format": "playwright", "path": "reports/plotlot-playwright.json"},
                browser_artifact="browser/plotlot/index.html",
                expected_test_count=21,
                environment={
                    "PLAYWRIGHT_JSON_OUTPUT_FILE": str(plotlot_browser),
                    "PLAYWRIGHT_HTML_OUTPUT_DIR": str(artifact_root / "browser/plotlot"),
                },
            ),
            Lane("byright-install", "byright", ["pnpm", "install", "--frozen-lockfile"]),
            Lane(
                "byright-playwright-install",
                "byright",
                ["pnpm", "exec", "playwright", "install", "chromium"],
            ),
            Lane("byright-hygiene", "byright", ["pnpm", "hygiene"]),
            Lane("byright-lint", "byright", ["pnpm", "lint"]),
            Lane("byright-typecheck", "byright", ["pnpm", "typecheck"]),
            Lane(
                "byright-vitest",
                "byright",
                [
                    "pnpm",
                    "exec",
                    "vitest",
                    "run",
                    "--reporter=json",
                    f"--outputFile={byright_report}",
                ],
                report={"format": "vitest", "path": "reports/byright-vitest.json"},
            ),
            Lane("byright-persistence", "byright", ["pnpm", "test:persistence"]),
            Lane("byright-build", "byright", ["pnpm", "build"]),
            Lane(
                "byright-playwright",
                "byright",
                ["pnpm", "exec", "playwright", "test", "--reporter=json,html"],
                report={"format": "playwright", "path": "reports/byright-playwright.json"},
                browser_artifact="browser/byright/index.html",
                environment={
                    "PLAYWRIGHT_JSON_OUTPUT_FILE": str(byright_browser),
                    "PLAYWRIGHT_HTML_OUTPUT_DIR": str(artifact_root / "browser/byright"),
                },
            ),
        )
    ]
