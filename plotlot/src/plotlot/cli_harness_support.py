from __future__ import annotations

from dataclasses import dataclass
import json

from plotlot.harness.contracts import JsonObject, SourceMode


@dataclass(frozen=True, slots=True)
class ParsedOption:
    items: dict[str, list[str]]
    flags: frozenset[str]


def parse_options(args: list[str]) -> ParsedOption:
    items: dict[str, list[str]] = {}
    flags: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token.startswith("--"):
            flags.append(token)
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                items.setdefault(token, []).append(args[index + 1])
                index += 2
            else:
                index += 1
        else:
            index += 1
    return ParsedOption(items=items, flags=frozenset(flags))


def option_value(options: ParsedOption, name: str) -> str | None:
    values = options.items.get(name, [])
    if not values:
        return None
    return values[0]


def source_mode_option(options: ParsedOption) -> SourceMode:
    value = option_value(options, "--source-mode")
    if value is None:
        return SourceMode.FIXTURE
    return SourceMode(value)


def assumptions_from_options(options: ParsedOption) -> JsonObject:
    pairs = options.items.get("--assumption", [])
    parsed: JsonObject = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        parsed[key] = coerce_scalar(value)
    raw_json = option_value(options, "--assumptions-json")
    if raw_json is not None:
        decoded = json.loads(raw_json)
        if not isinstance(decoded, dict):
            raise ValueError("--assumptions-json must decode to an object.")
        for key, value in decoded.items():
            parsed[str(key)] = value
    return parsed


def coerce_scalar(value: str) -> int | float | str:
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value
