from __future__ import annotations

import json

from plotlot.cli_harness_support import ParsedOption, option_value, parse_options
from plotlot.harness.contracts import (
    EvidenceId,
    MemoryId,
    MemoryType,
    ProjectId,
    RunId,
    SiteId,
    WorkspaceId,
)
from plotlot.harness.memory_store import (
    MemoryListFilter,
    MemoryNotFoundError,
    MemoryUpdateRequest,
    MemoryWriteRequest,
    default_memory_store,
)


def memory_command(args: list[str]) -> int:
    if not args:
        return _usage()
    store = default_memory_store()
    try:
        match args[0]:
            case "write":
                options = parse_options(args[1:])
                workspace_id = option_value(options, "--workspace-id")
                memory_type = option_value(options, "--memory-type")
                content = option_value(options, "--content")
                if workspace_id is None or memory_type is None or content is None:
                    return _usage()
                written = store.write_memory(
                    _write_request(options, workspace_id, memory_type, content)
                )
                print(json.dumps(written.model_dump(mode="json")))
                return 0
            case "list":
                listed = store.list_memory(_list_filter(parse_options(args[1:])))
                print(json.dumps({"memory": [item.model_dump(mode="json") for item in listed]}))
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(store.get_memory(MemoryId(args[1])).model_dump(mode="json")))
                return 0
            case "update" if len(args) >= 2:
                options = parse_options(args[2:])
                content = option_value(options, "--content")
                updated = store.update_memory(
                    MemoryId(args[1]),
                    MemoryUpdateRequest(content=content),
                )
                print(json.dumps(updated.model_dump(mode="json")))
                return 0
            case _:
                return _usage()
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2
    except MemoryNotFoundError as exc:
        print(json.dumps({"error": "memory_not_found", "detail": str(exc)}))
        return 1


def _write_request(
    options: ParsedOption,
    workspace_id: str,
    memory_type: str,
    content: str,
) -> MemoryWriteRequest:
    project_id = option_value(options, "--project-id")
    site_id = option_value(options, "--site-id")
    source_run_id = option_value(options, "--source-run-id")
    return MemoryWriteRequest(
        workspace_id=WorkspaceId(workspace_id),
        project_id=ProjectId(project_id) if project_id else None,
        site_id=SiteId(site_id) if site_id else None,
        memory_type=MemoryType(memory_type),
        content=content,
        source_run_id=RunId(source_run_id) if source_run_id else None,
        evidence_ids=[EvidenceId(value) for value in options.items.get("--evidence-id", [])],
    )


def _list_filter(options: ParsedOption) -> MemoryListFilter:
    workspace_id = option_value(options, "--workspace-id")
    project_id = option_value(options, "--project-id")
    site_id = option_value(options, "--site-id")
    source_run_id = option_value(options, "--source-run-id")
    memory_type = option_value(options, "--memory-type")
    return MemoryListFilter(
        workspace_id=WorkspaceId(workspace_id) if workspace_id else None,
        project_id=ProjectId(project_id) if project_id else None,
        site_id=SiteId(site_id) if site_id else None,
        source_run_id=RunId(source_run_id) if source_run_id else None,
        memory_type=MemoryType(memory_type) if memory_type else None,
    )


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": (
                    "plotlot memory <write|list|show|update> "
                    "--workspace-id WORKSPACE_ID --memory-type MEMORY_TYPE --content CONTENT"
                ),
            }
        )
    )
    return 2
