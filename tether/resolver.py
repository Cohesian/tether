"""Pure projections between K contribution targets and store URIs."""

from __future__ import annotations

import json
import re
import string
import tomllib
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit


FIELDS = {"id", "path", "contributor", "domain", "format"}


class ResolverError(ValueError):
    """A user-facing target, descriptor, or resolution error."""


def _required_string(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ResolverError(f"{field} must be a non-empty string")
    return raw


def _normalize_id(raw: object) -> str:
    value = _required_string(raw, "selector.id")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ResolverError(f"invalid selector.id: {value!r}") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ResolverError("selector.id must be a canonical UUIDv4")
    return value


def _normalize_path(raw: object) -> str:
    value = _required_string(raw, "selector.path")
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        raise ResolverError(f"invalid selector.path: {value!r}")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ResolverError(f"invalid selector.path: {value!r}")
    return PurePosixPath(value).as_posix()


def normalize_selector(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ResolverError("selector must be an object")
    node_id = raw.get("id")
    rooted_path = raw.get("path")
    if node_id is None and rooted_path is None:
        raise ResolverError("selector requires id, path, or both")
    selector: dict[str, str] = {}
    if node_id is not None:
        selector["id"] = _normalize_id(node_id)
    if rooted_path is not None:
        selector["path"] = _normalize_path(rooted_path)
    return selector


def normalize_target(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResolverError("target must be an object")
    selector = raw.get("selector")
    contribution = raw.get("contribution")
    if not isinstance(selector, dict) or not isinstance(contribution, dict):
        raise ResolverError("target requires selector and contribution objects")

    return {
        "selector": normalize_selector(selector),
        "contribution": {
            field: _required_string(contribution.get(field), f"contribution.{field}")
            for field in ("contributor", "domain", "format")
        },
    }


def _template_fields(pattern: str) -> list[str]:
    fields: list[str] = []
    try:
        parsed = string.Formatter().parse(pattern)
        for _, field, format_spec, conversion in parsed:
            if field is None:
                continue
            if field not in FIELDS:
                raise ResolverError(f"unsupported template field: {field!r}")
            if format_spec or conversion:
                raise ResolverError(
                    "template formatting and conversion are unsupported"
                )
            if field in fields:
                raise ResolverError(f"template field is repeated: {field!r}")
            fields.append(field)
    except ValueError as exc:
        raise ResolverError(f"invalid template pattern: {pattern!r}") from exc
    return fields


def normalize_descriptor(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResolverError("store descriptor must be an object")
    if raw.get("version") != 1:
        raise ResolverError("store descriptor version must be 1")

    descriptor = {
        "version": 1,
        "store": _required_string(raw.get("store"), "descriptor.store"),
        "contributor": _required_string(
            raw.get("contributor"), "descriptor.contributor"
        ),
        "strategy": _required_string(raw.get("strategy"), "descriptor.strategy"),
    }
    domain = raw.get("domain")
    if domain is not None:
        descriptor["domain"] = _required_string(domain, "descriptor.domain")

    if descriptor["strategy"] == "template":
        origin = _required_string(raw.get("origin"), "descriptor.origin")
        if not urlsplit(origin).scheme:
            raise ResolverError("descriptor.origin must be an absolute URI")
        pattern = _required_string(raw.get("pattern"), "descriptor.pattern")
        _template_fields(pattern)
        descriptor.update(origin=origin.rstrip("/"), pattern=pattern)
        return descriptor

    if descriptor["strategy"] == "map":
        locations = raw.get("locations", [])
        if not isinstance(locations, list):
            raise ResolverError("descriptor.locations must be a list")
        normalized_locations: list[dict[str, Any]] = []
        for entry in locations:
            if not isinstance(entry, dict):
                raise ResolverError("each mapped location must be an object")
            normalized_locations.append(
                {
                    "target": normalize_target(entry.get("target")),
                    "uri": _absolute_uri(entry.get("uri")),
                }
            )
        descriptor["locations"] = normalized_locations
        return descriptor

    raise ResolverError(f"unsupported descriptor strategy: {descriptor['strategy']!r}")


def _absolute_uri(raw: object) -> str:
    value = _required_string(raw, "uri")
    if not urlsplit(value).scheme:
        raise ResolverError(f"URI must be absolute: {value!r}")
    return value


def _descriptor_accepts(target: dict[str, Any], descriptor: dict[str, Any]) -> None:
    contribution = target["contribution"]
    if contribution["contributor"] != descriptor["contributor"]:
        raise ResolverError("target contributor does not match store descriptor")
    if "domain" in descriptor and contribution["domain"] != descriptor["domain"]:
        raise ResolverError("target domain does not match store descriptor")


def _target_fields(target: dict[str, Any]) -> dict[str, str]:
    return {**target["selector"], **target["contribution"]}


def _same_target(query: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if query["contribution"] != candidate["contribution"]:
        return False
    for field, value in query["selector"].items():
        if candidate["selector"].get(field) != value:
            return False
    return True


def _template_uri(target: dict[str, Any], descriptor: dict[str, Any]) -> str:
    fields = _target_fields(target)
    required = _template_fields(descriptor["pattern"])
    missing = [field for field in required if field not in fields]
    if missing:
        raise ResolverError(f"target lacks template fields: {', '.join(missing)}")
    rendered = descriptor["pattern"].format_map(fields)
    relative = PurePosixPath(rendered)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ResolverError("template must render a safe relative URI path")
    encoded = quote(relative.as_posix(), safe="/-._~")
    return f"{descriptor['origin']}/{encoded}"


def resolve(target: object, descriptor: object) -> dict[str, Any]:
    normalized_target = normalize_target(target)
    normalized_descriptor = normalize_descriptor(descriptor)
    _descriptor_accepts(normalized_target, normalized_descriptor)

    if normalized_descriptor["strategy"] == "template":
        uri = _template_uri(normalized_target, normalized_descriptor)
    else:
        matches = [
            entry["uri"]
            for entry in normalized_descriptor["locations"]
            if _same_target(normalized_target, entry["target"])
        ]
        if not matches:
            raise ResolverError("target is absent from the explicit URI map")
        if len(set(matches)) != 1:
            raise ResolverError("target maps to several URIs in one descriptor")
        uri = matches[0]

    return {
        "target": normalized_target,
        "store": {
            key: normalized_descriptor[key]
            for key in ("store", "contributor", "domain", "strategy")
            if key in normalized_descriptor
        },
        "uri": uri,
    }


def _template_regex(pattern: str) -> re.Pattern[str]:
    pieces: list[str] = []
    for literal, field, _, _ in string.Formatter().parse(pattern):
        pieces.append(re.escape(literal))
        if field is not None:
            expression = ".+" if field == "path" else "[^/]+"
            pieces.append(f"(?P<{field}>{expression})")
    return re.compile("^" + "".join(pieces) + "$")


def _identify_template(uri: str, descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    prefix = f"{descriptor['origin']}/"
    if not uri.startswith(prefix):
        return []
    relative = unquote(uri[len(prefix) :])
    match = _template_regex(descriptor["pattern"]).fullmatch(relative)
    if match is None:
        return []
    fields = {
        key: value
        for key, value in match.groupdict().items()
        if value is not None
    }
    contributor = fields.get("contributor", descriptor["contributor"])
    domain = fields.get("domain", descriptor.get("domain"))
    content_format = fields.get("format")
    if domain is None or content_format is None:
        raise ResolverError(
            "reverse template resolution requires domain and format from the "
            "descriptor or URI pattern"
        )
    selector = {key: fields[key] for key in ("id", "path") if key in fields}
    return [
        normalize_target(
            {
                "selector": selector,
                "contribution": {
                    "contributor": contributor,
                    "domain": domain,
                    "format": content_format,
                },
            }
        )
    ]


def identify(uri: object, descriptor: object) -> list[dict[str, Any]]:
    normalized_uri = _absolute_uri(uri)
    normalized_descriptor = normalize_descriptor(descriptor)
    if normalized_descriptor["strategy"] == "template":
        return _identify_template(normalized_uri, normalized_descriptor)
    return [
        entry["target"]
        for entry in normalized_descriptor["locations"]
        if entry["uri"] == normalized_uri
    ]


def resolve_discoveries(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict) and "discoveries" in payload:
        discoveries = payload["discoveries"]
    elif isinstance(payload, dict) and {"target", "stores"} <= payload.keys():
        discoveries = [payload]
    elif isinstance(payload, list):
        discoveries = payload
    else:
        raise ResolverError("input must contain one discovery or a discoveries list")
    if not isinstance(discoveries, list):
        raise ResolverError("discoveries must be a list")

    locations: list[dict[str, Any]] = []
    for discovery in discoveries:
        if not isinstance(discovery, dict):
            raise ResolverError("each discovery must be an object")
        stores = discovery.get("stores")
        if not isinstance(stores, list):
            raise ResolverError("discovery stores must be a list")
        for store in stores:
            if not isinstance(store, dict) or not isinstance(
                store.get("descriptor"), dict
            ):
                raise ResolverError("each store requires an embedded descriptor")
            locations.append(resolve(discovery.get("target"), store["descriptor"]))
    return {"version": 1, "locations": locations}


def load_document(path: Path | None) -> Any:
    if path is None:
        import sys

        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise ResolverError(f"invalid JSON input: {exc}") from exc
    try:
        if path.suffix == ".toml":
            with path.open("rb") as handle:
                return tomllib.load(handle)
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResolverError(f"input not found: {path}") from exc
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ResolverError(f"invalid input in {path}: {exc}") from exc
