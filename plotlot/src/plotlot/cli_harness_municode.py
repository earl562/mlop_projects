from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options, source_mode_option
from plotlot.harness.municode_source import (
    MunicodeModeUnsupportedError,
    MunicodeSectionNotFoundError,
    extract_ordinance_rules,
    get_municode_section,
    search_municode,
)


def municode_command(args: list[str]) -> int:
    if not args:
        return _usage()
    try:
        match args[0]:
            case "search":
                options = parse_options(args[1:])
                jurisdiction = option_value(options, "--jurisdiction")
                query = option_value(options, "--query")
                if jurisdiction is None or query is None:
                    return _usage()
                mode = source_mode_option(options)
                results = search_municode(
                    jurisdiction=jurisdiction,
                    query=query,
                    source_mode=mode,
                )
                print(
                    json.dumps(
                        {
                            "source_mode": mode.value,
                            "results": [result.model_dump(mode="json") for result in results],
                        }
                    )
                )
                return 0
            case "section":
                options = parse_options(args[1:])
                section_id = option_value(options, "--section-id")
                if section_id is None:
                    return _usage()
                section = get_municode_section(section_id, source_mode=source_mode_option(options))
                print(json.dumps({"section": section.model_dump(mode="json")}))
                return 0
            case "extract-rules":
                options = parse_options(args[1:])
                section_id = option_value(options, "--section-id")
                if section_id is None:
                    return _usage()
                section = get_municode_section(section_id, source_mode=source_mode_option(options))
                print(json.dumps(extract_ordinance_rules(section).model_dump(mode="json")))
                return 0
            case _:
                return _usage()
    except MunicodeSectionNotFoundError as exc:
        print(json.dumps({"error": "municode_section_not_found", "detail": str(exc)}))
        return 1
    except MunicodeModeUnsupportedError as exc:
        print(json.dumps({"error": "municode_mode_unsupported", "detail": str(exc)}))
        return 1


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": (
                    "plotlot municode <search|section|extract-rules> "
                    "--jurisdiction JURISDICTION --query QUERY"
                ),
            }
        )
    )
    return 2
