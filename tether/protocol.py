"""Declarative contributor packages and their semantic projections."""

from __future__ import annotations

import string
import tomllib
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .resolver import (
    ResolverError,
    identify,
    normalize_descriptor,
    normalize_selector,
    normalize_target,
    resolve_discoveries,
)


SUPPORTED_PROTOCOL_VERSION = 1


def _required_string(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ResolverError(f"{field} must be a non-empty string")
    return raw


def _protocol_name(raw: object, field: str) -> str:
    value = _required_string(raw, field)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value) is None:
        raise ResolverError(
            f"{field} must use letters, numbers, underscores, or hyphens"
        )
    return value


def _string_list(raw: object, field: str) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ResolverError(f"{field} must be a non-empty string list")
    values = [_required_string(value, field) for value in raw]
    if len(values) != len(set(values)):
        raise ResolverError(f"{field} contains duplicates")
    return values


def _protocol_name_list(raw: object, field: str) -> list[str]:
    values = _string_list(raw, field)
    return [_protocol_name(value, field) for value in values]


def _package_path(root: Path, raw: object, field: str) -> Path:
    value = _required_string(raw, field)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolverError(f"{field} must stay inside the contributor package")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ResolverError(
            f"{field} must stay inside the contributor package"
        ) from exc
    return candidate


def _load_toml(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ResolverError(f"{label} not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ResolverError(f"invalid TOML in {path}: {exc}") from exc


def load_contributor(path: Path) -> dict[str, Any]:
    config_path = (
        path / "contributor.toml" if path.is_dir() else path
    ).resolve()
    raw = _load_toml(config_path, "contributor protocol")
    if raw.get("version") != 1:
        raise ResolverError("contributor protocol version must be 1")

    contributor = raw.get("contributor")
    domains = raw.get("domains")
    stores = raw.get("stores")
    bindings = raw.get("bindings")
    if not isinstance(contributor, dict):
        raise ResolverError("contributor protocol requires [contributor]")
    contributor_id = _protocol_name(contributor.get("id"), "contributor.id")
    if not isinstance(domains, dict) or not domains:
        raise ResolverError("contributor protocol requires at least one domain")
    if not isinstance(stores, dict) or not stores:
        raise ResolverError("contributor protocol requires at least one store")
    if not isinstance(bindings, list) or not bindings:
        raise ResolverError("contributor protocol requires at least one binding")

    normalized_domains: dict[str, dict[str, Any]] = {}
    for name, domain in domains.items():
        domain_name = _protocol_name(name, "domain name")
        if not isinstance(domain, dict):
            raise ResolverError(f"domains.{domain_name} must be a table")
        normalized_domains[domain_name] = {
            "formats": _protocol_name_list(
                domain.get("formats"), f"domains.{domain_name}.formats"
            )
        }

    normalized_stores: dict[str, dict[str, Any]] = {}
    for name, store in stores.items():
        store_name = _protocol_name(name, "store name")
        if not isinstance(store, dict):
            raise ResolverError(f"stores.{store_name} must be a table")
        kind = _required_string(store.get("kind"), f"stores.{store_name}.kind")
        strategy = _required_string(
            store.get("strategy"), f"stores.{store_name}.strategy"
        )
        enabled = store.get("enabled")
        if kind not in {"directory", "remote"}:
            raise ResolverError(f"unsupported store kind: {kind!r}")
        if strategy not in {"template", "map"}:
            raise ResolverError(f"unsupported store strategy: {strategy!r}")
        if not isinstance(enabled, bool):
            raise ResolverError(f"stores.{store_name}.enabled must be boolean")
        normalized_store: dict[str, Any] = {
            "kind": kind,
            "enabled": enabled,
            "strategy": strategy,
        }
        if kind == "directory":
            origin = _required_string(
                store.get("origin"), f"stores.{store_name}.origin"
            )
            normalized_store["origin"] = _package_path(
                config_path.parent, origin, f"stores.{store_name}.origin"
            ).as_uri()
        elif strategy == "template":
            origin = _required_string(
                store.get("origin"), f"stores.{store_name}.origin"
            )
            if not urlsplit(origin).scheme:
                raise ResolverError(
                    f"stores.{store_name}.origin must be an absolute URI"
                )
            else:
                normalized_store["origin"] = origin.rstrip("/")
        normalized_stores[store_name] = normalized_store

    normalized_bindings: list[dict[str, Any]] = []
    seen_bindings: set[tuple[str, str]] = set()
    for index, binding in enumerate(bindings):
        label = f"bindings[{index}]"
        if not isinstance(binding, dict):
            raise ResolverError(f"{label} must be a table")
        domain = _required_string(binding.get("domain"), f"{label}.domain")
        store = _required_string(binding.get("store"), f"{label}.store")
        if domain not in normalized_domains:
            raise ResolverError(f"{label} names unknown domain {domain!r}")
        if store not in normalized_stores:
            raise ResolverError(f"{label} names unknown store {store!r}")
        identity = (domain, store)
        if identity in seen_bindings:
            raise ResolverError(f"duplicate domain-store binding: {identity!r}")
        seen_bindings.add(identity)
        formats = _protocol_name_list(
            binding.get("formats"), f"{label}.formats"
        )
        if not set(formats) <= set(normalized_domains[domain]["formats"]):
            raise ResolverError(f"{label}.formats exceeds its domain formats")
        inventory = _package_path(
            config_path.parent, binding.get("inventory"), f"{label}.inventory"
        )
        normalized_binding: dict[str, Any] = {
            "domain": domain,
            "store": store,
            "formats": formats,
            "inventory": inventory,
        }
        if normalized_stores[store]["strategy"] == "template":
            pattern = _required_string(binding.get("pattern"), f"{label}.pattern")
            _validate_pattern(pattern, label)
            normalized_binding["pattern"] = pattern
        elif "pattern" in binding:
            raise ResolverError(f"{label}.pattern is invalid for a map store")
        normalized_bindings.append(normalized_binding)

    return {
        "version": 1,
        "path": config_path,
        "contributor": contributor_id,
        "domains": normalized_domains,
        "stores": normalized_stores,
        "bindings": normalized_bindings,
    }


def check_contributor(path: Path) -> dict[str, Any]:
    """Report protocol compatibility, then validate supported packages."""

    config_path = (path / "contributor.toml" if path.is_dir() else path).resolve()
    raw = _load_toml(config_path, "contributor protocol")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ResolverError("contributor protocol version must be an integer")
    if version < SUPPORTED_PROTOCOL_VERSION:
        return {
            "version": 1,
            "valid": False,
            "compatibility": "older",
            "protocol_version": version,
            "supported_version": SUPPORTED_PROTOCOL_VERSION,
            "message": "contributor protocol requires migration before validation",
        }
    if version > SUPPORTED_PROTOCOL_VERSION:
        return {
            "version": 1,
            "valid": False,
            "compatibility": "newer",
            "protocol_version": version,
            "supported_version": SUPPORTED_PROTOCOL_VERSION,
            "message": "installed Tether is older than this contributor protocol",
        }
    result = validate_contributor(load_contributor(config_path))
    return {
        **result,
        "compatibility": "compatible",
        "protocol_version": version,
        "supported_version": SUPPORTED_PROTOCOL_VERSION,
    }


def _validate_pattern(pattern: str, label: str) -> None:
    allowed = {"id", "path", "contributor", "domain", "format"}
    try:
        fields = [
            field
            for _, field, format_spec, conversion in string.Formatter().parse(pattern)
            if field is not None
            and not _reject_formatting(format_spec, conversion, label)
        ]
    except ValueError as exc:
        raise ResolverError(f"{label}.pattern is invalid") from exc
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ResolverError(
            f"{label}.pattern has unsupported fields: {', '.join(unknown)}"
        )
    if not {"id", "path"} & set(fields):
        raise ResolverError(f"{label}.pattern requires id or path")


def _reject_formatting(format_spec: str, conversion: str | None, label: str) -> bool:
    if format_spec or conversion:
        raise ResolverError(f"{label}.pattern formatting is unsupported")
    return False


def _load_inventory(binding: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _load_toml(binding["inventory"], "binding inventory")
    if raw.get("version") != 1:
        raise ResolverError(
            f"inventory version must be 1: {binding['inventory']}"
        )
    routes = raw.get("route", [])
    if not isinstance(routes, list) or not all(
        isinstance(route, dict) for route in routes
    ):
        raise ResolverError(f"inventory routes must be tables: {binding['inventory']}")
    return routes


def _target(
    package: dict[str, Any], binding: dict[str, Any], route: dict[str, Any]
) -> dict[str, Any]:
    return normalize_target(
        {
            "selector": {
                key: route[key] for key in ("id", "path") if key in route
            },
            "contribution": {
                "contributor": package["contributor"],
                "domain": binding["domain"],
                "format": route.get("format"),
            },
        }
    )


def _target_fields(target: dict[str, Any]) -> dict[str, str]:
    return {**target["selector"], **target["contribution"]}


def _target_matches(query: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return query["contribution"] == candidate["contribution"] and all(
        candidate["selector"].get(key) == value
        for key, value in query["selector"].items()
    )


def _validate_route(
    package: dict[str, Any],
    binding: dict[str, Any],
    route: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    target = _target(package, binding, route)
    content_format = target["contribution"]["format"]
    if content_format not in binding["formats"]:
        raise ResolverError(
            f"inventory format is outside its binding: {binding['inventory']}"
        )
    store = package["stores"][binding["store"]]
    if store["strategy"] == "map":
        _descriptor(package, binding, [route])
        return target, None
    try:
        rendered = binding["pattern"].format_map(_target_fields(target))
    except (KeyError, ValueError) as exc:
        raise ResolverError(
            f"binding pattern cannot represent route: {binding['inventory']}"
        ) from exc
    location = route.get("location")
    if location is not None and location != rendered:
        raise ResolverError(
            f"route location does not match binding pattern: {binding['inventory']}"
        )
    return target, rendered


def _mapped_uri(
    package: dict[str, Any],
    binding: dict[str, Any],
    route: dict[str, Any],
) -> str | None:
    store = package["stores"][binding["store"]]
    if store["kind"] != "directory":
        return route.get("uri")

    location = _required_string(
        route.get("location"),
        f"mapped directory location in {binding['inventory']}",
    )
    relative = Path(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolverError(
            f"mapped directory location must stay inside {binding['inventory']}"
        )
    origin = Path(unquote(urlsplit(store["origin"]).path)).resolve()
    candidate = (origin / relative).resolve()
    try:
        candidate.relative_to(origin)
    except ValueError as exc:
        raise ResolverError(
            f"mapped directory location must stay inside {binding['inventory']}"
        ) from exc
    return candidate.as_uri()


def _descriptor(
    package: dict[str, Any],
    binding: dict[str, Any],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    store_name = binding["store"]
    store = package["stores"][store_name]
    descriptor: dict[str, Any] = {
        "version": 1,
        "store": store_name,
        "contributor": package["contributor"],
        "domain": binding["domain"],
        "strategy": store["strategy"],
    }
    if store["strategy"] == "template":
        descriptor.update(origin=store["origin"], pattern=binding["pattern"])
    else:
        descriptor["locations"] = [
            {
                "target": _target(package, binding, route),
                "uri": _mapped_uri(package, binding, route),
            }
            for route in routes
        ]
    return normalize_descriptor(descriptor)


def _route_available(
    package: dict[str, Any],
    binding: dict[str, Any],
    route: dict[str, Any],
) -> bool:
    store = package["stores"][binding["store"]]
    _, rendered = _validate_route(package, binding, route)
    if not store["enabled"]:
        return False
    if store["strategy"] == "map":
        if store["kind"] == "directory":
            uri = _mapped_uri(package, binding, route)
            assert uri is not None
            return Path(unquote(urlsplit(uri).path)).exists()
        return True
    if store["kind"] == "directory":
        origin = Path(unquote(urlsplit(store["origin"]).path))
        assert rendered is not None
        return (origin / rendered).exists()
    return True


def validate_contributor(package: dict[str, Any]) -> dict[str, Any]:
    route_records: set[tuple[str, str, str]] = set()
    resources: set[tuple[str, str, str]] = set()
    global_ids: dict[str, str] = {}
    global_paths: dict[str, str] = {}
    for binding in package["bindings"]:
        routes = _load_inventory(binding)
        ids: dict[str, str] = {}
        paths: dict[str, str] = {}
        seen: set[tuple[str, str]] = set()
        for route in routes:
            target, _ = _validate_route(package, binding, route)
            selector = target["selector"]
            node_id = selector.get("id")
            rooted_path = selector.get("path")
            content_format = target["contribution"]["format"]
            if node_id is not None and rooted_path is not None:
                if node_id in ids and ids[node_id] != rooted_path:
                    raise ResolverError(
                        "inventory maps one id to several paths: "
                        f"{binding['inventory']}"
                    )
                if rooted_path in paths and paths[rooted_path] != node_id:
                    raise ResolverError(
                        "inventory maps one path to several ids: "
                        f"{binding['inventory']}"
                    )
                ids[node_id] = rooted_path
                paths[rooted_path] = node_id
                if node_id in global_ids and global_ids[node_id] != rooted_path:
                    raise ResolverError(
                        "contributor inventories map one id to several paths"
                    )
                if (
                    rooted_path in global_paths
                    and global_paths[rooted_path] != node_id
                ):
                    raise ResolverError(
                        "contributor inventories map one path to several ids"
                    )
                global_ids[node_id] = rooted_path
                global_paths[rooted_path] = node_id
            identity = (node_id or rooted_path or "", content_format)
            if identity in seen:
                raise ResolverError(
                    f"duplicate route in inventory: {binding['inventory']}"
                )
            seen.add(identity)
            route_records.add(
                (str(binding["inventory"]), identity[0], content_format)
            )
            resources.add(
                (
                    node_id or rooted_path or "",
                    binding["domain"],
                    content_format,
                )
            )
    return {
        "version": 1,
        "valid": True,
        "contributor": package["contributor"],
        "domains": len(package["domains"]),
        "stores": len(package["stores"]),
        "bindings": len(package["bindings"]),
        "routes": len(route_records),
        "resources": len(resources),
    }


def inspect_contributor(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "contributor": package["contributor"],
        "domains": [
            {"name": name, "formats": domain["formats"]}
            for name, domain in sorted(package["domains"].items())
        ],
        "stores": [
            {"name": name, **store}
            for name, store in sorted(package["stores"].items())
        ],
        "bindings": [
            {
                key: str(value) if key == "inventory" else value
                for key, value in binding.items()
            }
            for binding in package["bindings"]
        ],
    }


def discover_contributor(
    package: dict[str, Any],
    *,
    node_id: str | None = None,
    rooted_path: str | None = None,
    domain: str | None = None,
    content_format: str | None = None,
    store: str | None = None,
) -> dict[str, Any]:
    if domain is not None and domain not in package["domains"]:
        raise ResolverError(f"unknown contributor domain: {domain!r}")
    if store is not None and store not in package["stores"]:
        raise ResolverError(f"unknown contributor store: {store!r}")
    admitted_formats = (
        set(package["domains"][domain]["formats"])
        if domain is not None
        else {
            value
            for spec in package["domains"].values()
            for value in spec["formats"]
        }
    )
    if content_format is not None and content_format not in admitted_formats:
        raise ResolverError(f"unknown format for selected domain: {content_format!r}")
    query_selector = (
        normalize_selector(
            {
                key: value
                for key, value in {"id": node_id, "path": rooted_path}.items()
                if value is not None
            }
        )
        if node_id is not None or rooted_path is not None
        else {}
    )
    selected: dict[
        tuple[str | None, str | None, str, str], dict[str, Any]
    ] = {}
    id_seen = False
    path_seen = False
    pair_seen = False
    for binding in package["bindings"]:
        if domain is not None and binding["domain"] != domain:
            continue
        if store is not None and binding["store"] != store:
            continue
        routes = _load_inventory(binding)
        if "id" in query_selector and "path" in query_selector:
            id_seen = id_seen or any(
                route.get("id") == query_selector["id"] for route in routes
            )
            path_seen = path_seen or any(
                route.get("path") == query_selector["path"] for route in routes
            )
            pair_seen = pair_seen or any(
                route.get("id") == query_selector["id"]
                and route.get("path") == query_selector["path"]
                for route in routes
            )
        available_routes = [
            route
            for route in routes
            if _route_available(package, binding, route)
            and (
                "id" not in query_selector
                or route.get("id") == query_selector["id"]
            )
            and (
                "path" not in query_selector
                or route.get("path") == query_selector["path"]
            )
            and (content_format is None or route.get("format") == content_format)
        ]
        for route in available_routes:
            target = _target(package, binding, route)
            selector = target["selector"]
            contribution = target["contribution"]
            key = (
                selector.get("id"),
                selector.get("path"),
                contribution["domain"],
                contribution["format"],
            )
            discovery = selected.setdefault(
                key, {"target": target, "stores": []}
            )
            discovery["stores"].append(
                {
                    "name": binding["store"],
                    "descriptor": _descriptor(package, binding, [route]),
                }
            )
    if (
        "id" in query_selector
        and "path" in query_selector
        and not pair_seen
        and (id_seen or path_seen)
    ):
        raise ResolverError("id and path do not identify the same target")
    discoveries = sorted(
        selected.values(),
        key=lambda item: (
            item["target"]["selector"].get("path", ""),
            item["target"]["contribution"]["domain"],
            item["target"]["contribution"]["format"],
        ),
    )
    return {
        "version": 1,
        "contributor": package["contributor"],
        "discoveries": discoveries,
    }


def project_contributor(
    package: dict[str, Any], **filters: str | None
) -> dict[str, Any]:
    return resolve_discoveries(discover_contributor(package, **filters))


def identify_contributor(
    package: dict[str, Any], uri: str
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for binding in package["bindings"]:
        store = package["stores"][binding["store"]]
        if not store["enabled"]:
            continue
        routes = [
            route
            for route in _load_inventory(binding)
            if _route_available(package, binding, route)
        ]
        descriptor = _descriptor(package, binding, routes)
        candidates = [_target(package, binding, route) for route in routes]
        for query in identify(uri, descriptor):
            for target in candidates:
                if _target_matches(query, target):
                    matches.append(
                        {
                            "store": binding["store"],
                            "target": target,
                        }
                    )
    return {"version": 1, "uri": uri, "matches": matches}


def contributor_template(contributor: str, domain: str, formats: list[str]) -> str:
    contributor = _protocol_name(contributor, "contributor id")
    domain = _protocol_name(domain, "domain")
    formats = [_protocol_name(value, "format") for value in formats]
    if not formats or len(formats) != len(set(formats)):
        raise ResolverError("formats must be a non-empty unique list")
    formats_toml = ", ".join(f'"{value}"' for value in formats)
    return f'''version = 1

[contributor]
id = "{contributor}"

[domains.{domain}]
formats = [{formats_toml}]

[stores.local]
kind = "directory"
enabled = true
strategy = "template"
origin = "storage/local"

[[bindings]]
domain = "{domain}"
store = "local"
formats = [{formats_toml}]
inventory = "storage/local/routes.toml"
pattern = "{{path}}.{{format}}"
'''
