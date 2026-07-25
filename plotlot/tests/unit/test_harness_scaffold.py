from __future__ import annotations

import json

import pytest

from plotlot.harness.scaffold import ScaffoldTargetExistsError, scaffold_tool


def test_scaffold_tool_creates_contract_handler_manifest_fixture_test_and_docs(tmp_path) -> None:
    manifest = scaffold_tool("demo_tool", tmp_path)

    paths = {item.path: item for item in manifest.files}
    assert manifest.component_type == "tool"
    assert manifest.name == "demo_tool"
    assert "src/plotlot/harness/generated_tools/demo_tool/contract.py" in paths
    assert "src/plotlot/harness/generated_tools/demo_tool/handler.py" in paths
    assert "src/plotlot/harness/generated_tools/demo_tool/manifest.json" in paths
    assert "tests/unit/generated_tools/test_demo_tool.py" in paths
    assert all(item.status == "created" for item in manifest.files)

    contract_path = tmp_path / "src/plotlot/harness/generated_tools/demo_tool/contract.py"
    handler_path = tmp_path / "src/plotlot/harness/generated_tools/demo_tool/handler.py"
    compile(contract_path.read_text(encoding="utf-8"), str(contract_path), "exec")
    compile(handler_path.read_text(encoding="utf-8"), str(handler_path), "exec")

    manifest_path = tmp_path / "src/plotlot/harness/generated_tools/demo_tool/manifest.json"
    dumped = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert dumped["tool_name"] == "demo_tool"
    assert dumped["registry_symbol"] == "TOOL_SPEC"


def test_scaffold_tool_does_not_overwrite_without_force(tmp_path) -> None:
    scaffold_tool("demo_tool", tmp_path)

    with pytest.raises(ScaffoldTargetExistsError):
        scaffold_tool("demo_tool", tmp_path)


def test_scaffold_tool_force_overwrites_existing_files(tmp_path) -> None:
    scaffold_tool("demo_tool", tmp_path)
    forced = scaffold_tool("demo_tool", tmp_path, force=True)

    statuses = {item.status for item in forced.files}
    assert statuses == {"overwritten"}


def test_scaffold_tool_rejects_invalid_tool_name(tmp_path) -> None:
    with pytest.raises(ValueError):
        scaffold_tool("123 bad", tmp_path)
