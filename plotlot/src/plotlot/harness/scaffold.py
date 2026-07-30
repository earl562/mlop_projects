from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from plotlot.harness.contracts import (
    ScaffoldComponentType,
    ScaffoldFile,
    ScaffoldFileStatus,
    ScaffoldManifest,
)


@dataclass(frozen=True, slots=True)
class ScaffoldTargetExistsError(Exception):
    path: Path

    def __str__(self) -> str:
        return f"Scaffold target already exists: {self.path}"


@dataclass(frozen=True, slots=True)
class ScaffoldTemplateFile:
    relative_path: Path
    kind: str
    content: str


def scaffold_tool(name: str, target_root: Path, *, force: bool = False) -> ScaffoldManifest:
    normalized = _normalize_name(name)
    files = _tool_template_files(normalized)
    target_root = target_root.expanduser()
    if not force:
        _raise_if_any_target_exists(target_root, files)
    statuses = _write_template_files(target_root, files, force=force)
    return ScaffoldManifest(
        scaffold_id=f"scaffold_{uuid4().hex[:12]}",
        component_type=ScaffoldComponentType.TOOL,
        name=normalized,
        target_root=str(target_root),
        files=statuses,
        force=force,
        metadata={
            "registry_symbol": "TOOL_SPEC",
            "handler_symbol": "handle",
            "source": "plotlot_scaffold_tool_v1",
        },
    )


def _normalize_name(name: str) -> str:
    normalized = name.strip().replace("-", "_").lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized):
        raise ValueError("tool name must be lower snake case and start with a letter")
    return normalized


def _raise_if_any_target_exists(target_root: Path, files: list[ScaffoldTemplateFile]) -> None:
    for file in files:
        target = target_root / file.relative_path
        if target.exists():
            raise ScaffoldTargetExistsError(path=target)


def _write_template_files(
    target_root: Path,
    files: list[ScaffoldTemplateFile],
    *,
    force: bool,
) -> list[ScaffoldFile]:
    statuses: list[ScaffoldFile] = []
    for file in files:
        target = target_root / file.relative_path
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
        statuses.append(
            ScaffoldFile(
                path=str(file.relative_path),
                kind=file.kind,
                status=(
                    ScaffoldFileStatus.OVERWRITTEN
                    if force and existed
                    else ScaffoldFileStatus.CREATED
                ),
            )
        )
    return statuses


def _tool_template_files(name: str) -> list[ScaffoldTemplateFile]:
    base = Path("src") / "plotlot" / "harness" / "generated_tools" / name
    tests = Path("tests") / "unit" / "generated_tools" / f"test_{name}.py"
    docs = Path("docs") / "generated_tools" / f"{name}.md"
    return [
        ScaffoldTemplateFile(base / "__init__.py", "package", _init_template(name)),
        ScaffoldTemplateFile(base / "contract.py", "tool_contract", _contract_template(name)),
        ScaffoldTemplateFile(base / "handler.py", "tool_handler", _handler_template(name)),
        ScaffoldTemplateFile(base / "manifest.json", "tool_manifest", _manifest_template(name)),
        ScaffoldTemplateFile(base / "fixture.json", "fixture", _fixture_template(name)),
        ScaffoldTemplateFile(base / "policy.json", "policy_metadata", _policy_template(name)),
        ScaffoldTemplateFile(tests, "unit_test", _test_template(name)),
        ScaffoldTemplateFile(docs, "docs", _docs_template(name)),
    ]


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _init_template(name: str) -> str:
    return f'GENERATED_TOOL_NAME = "{name}"\n'


def _contract_template(name: str) -> str:
    class_name = _class_name(name)
    lines = [
        "from __future__ import annotations",
        "",
        "from pydantic import Field",
        "",
        "from plotlot.harness.contracts.base import HarnessContract, JsonObject",
        "",
        "",
        f"class {class_name}Input(HarnessContract):",
        f'    request_id: str = Field(default="{name}_fixture", min_length=1)',
        "",
        "",
        f"class {class_name}Output(HarnessContract):",
        '    status: str = Field(default="ok", min_length=1)',
        "    data: JsonObject = Field(default_factory=dict)",
    ]
    return "\n".join(lines) + "\n"


def _handler_template(name: str) -> str:
    class_name = _class_name(name)
    input_schema = '{"type": "object", "properties": {"request_id": {"type": "string"}}}'
    output_schema = '{"type": "object", "properties": {"status": {"type": "string"}}}'
    lines = [
        "from __future__ import annotations",
        "",
        "from plotlot.harness.contracts import JsonObject, PolicyPermission, ToolSpec",
        "",
        f"from .contract import {class_name}Input, {class_name}Output",
        "",
        "",
        "TOOL_SPEC = ToolSpec(",
        f'    name="{name}",',
        f'    description="Generated PlotLot harness tool: {name}",',
        f"    input_schema={input_schema},",
        f"    output_schema={output_schema},",
        "    permission=PolicyPermission.ALLOW,",
        '    evidence_behavior="records_evidence_or_calculation_when_material",',
        "    deterministic=True,",
        ")",
        "",
        "",
        "def handle(args: JsonObject) -> JsonObject:",
        f"    request = {class_name}Input.model_validate(args)",
        f'    result = {class_name}Output(data={{"request_id": request.request_id}})',
        '    return result.model_dump(mode="json")',
    ]
    return "\n".join(lines) + "\n"


def _manifest_template(name: str) -> str:
    return (
        json.dumps(
            {
                "schema": "plotlot.scaffold.tool.v1",
                "tool_name": name,
                "registry_symbol": "TOOL_SPEC",
                "handler_symbol": "handle",
                "fixture": "fixture.json",
                "policy": "policy.json",
            },
            indent=2,
        )
        + "\n"
    )


def _fixture_template(name: str) -> str:
    return json.dumps({"request_id": f"{name}_fixture"}, indent=2) + "\n"


def _policy_template(name: str) -> str:
    return (
        json.dumps(
            {
                "tool_name": name,
                "permission": "allow",
                "risk_level": "low",
                "policy_ids": [f"generated-{name}-allow"],
            },
            indent=2,
        )
        + "\n"
    )


def _test_template(name: str) -> str:
    class_name = _class_name(name)
    lines = [
        f"from plotlot.harness.generated_tools.{name}.contract import {class_name}Input",
        f"from plotlot.harness.generated_tools.{name}.handler import TOOL_SPEC, handle",
        "",
        "",
        f"def test_{name}_handler_returns_fixture_payload() -> None:",
        '    result = handle({"request_id": "fixture"})',
        "",
        f'    assert TOOL_SPEC.name == "{name}"',
        f'    assert {class_name}Input.model_validate({{"request_id": "fixture"}}).request_id == "fixture"',
        '    assert result["status"] == "ok"',
        '    assert result["data"]["request_id"] == "fixture"',
    ]
    return "\n".join(lines) + "\n"


def _docs_template(name: str) -> str:
    lines = [
        f"# Generated Tool: {name}",
        "",
        f"This scaffold was generated by `plotlot scaffold tool {name}`.",
        "",
        "Review the generated `TOOL_SPEC`, handler, fixture, policy metadata, and unit test",
        "before registering the tool in the production harness registry.",
    ]
    return "\n".join(lines) + "\n"
