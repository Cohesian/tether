"""Contributor protocol v2 parsing, validation, and projections."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

from .resolver import ResolverError, normalize_selector
from .resource_protocols import (
    normalize_protocol_id,
    normalize_sha256,
    verify_resource_digest,
)


NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _required_string(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ResolverError(f"{field} must be a non-empty string")
    return raw


def _name(raw: object, field: str) -> str:
    value = _required_string(raw, field)
    if NAME_RE.fullmatch(value) is None:
        raise ResolverError(
            f"{field} must use letters, numbers, underscores, or hyphens"
        )
    return value


def _hierarchy(raw: object, field: str = "hierarchy") -> tuple[str, ...]:
    if isinstance(raw, str):
        values = raw.split("/")
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        raise ResolverError(f"{field} must be a non-empty string list")
    if not values:
        raise ResolverError(f"{field} must be a non-empty string list")
    return tuple(_name(value, field) for value in values)


def _package_path(root: Path, raw: object, field: str) -> Path:
    value = _required_string(raw, field)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolverError(f"{field} must stay inside the contributor package")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ResolverError(f"{field} must stay inside the contributor package") from exc
    return candidate


def _load_toml(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ResolverError(f"{label} not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ResolverError(f"invalid TOML in {path}: {exc}") from exc


def _absolute_uri(raw: object, field: str) -> str:
    value = _required_string(raw, field)
    if not urlsplit(value).scheme:
        raise ResolverError(f"{field} must be an absolute URI")
    return value


def _directory_uri(origin: str, location: object, field: str) -> str:
    value = _required_string(location, field)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolverError(f"{field} must stay inside its directory store")
    root = Path(unquote(urlsplit(origin).path)).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ResolverError(f"{field} must stay inside its directory store") from exc
    return candidate.as_uri()


def normalize_v2_target(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResolverError("target must be an object")
    selector = normalize_selector(raw.get("selector"))
    contribution = raw.get("contribution")
    if not isinstance(contribution, dict):
        raise ResolverError("target requires a contribution object")
    return {
        "selector": selector,
        "contribution": {
            "contributor": _name(
                contribution.get("contributor"), "contribution.contributor"
            ),
            "hierarchy": list(
                _hierarchy(contribution.get("hierarchy"), "contribution.hierarchy")
            ),
            "key": _name(contribution.get("key"), "contribution.key"),
        },
    }


def _target_for(
    contributor: str,
    hierarchy: tuple[str, ...],
    resource: dict[str, Any],
) -> dict[str, Any]:
    selector_raw = {"id": resource.get("node_id")}
    if resource.get("path") is not None:
        selector_raw["path"] = resource["path"]
    return normalize_v2_target(
        {
            "selector": selector_raw,
            "contribution": {
                "contributor": contributor,
                "hierarchy": list(hierarchy),
                "key": resource.get("key"),
            },
        }
    )


def _normalize_store(
    root: Path, name: str, raw: object
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResolverError(f"stores.{name} must be a table")
    kind = _required_string(raw.get("kind"), f"stores.{name}.kind")
    if kind not in {"directory", "remote", "publication"}:
        raise ResolverError(f"unsupported v2 store kind: {kind!r}")
    enabled = raw.get("enabled")
    if not isinstance(enabled, bool):
        raise ResolverError(f"stores.{name}.enabled must be boolean")
    store: dict[str, Any] = {"kind": kind, "enabled": enabled}
    origin = raw.get("origin")
    if kind == "directory":
        store["origin"] = _package_path(root, origin, f"stores.{name}.origin").as_uri()
    elif origin is not None:
        store["origin"] = _absolute_uri(origin, f"stores.{name}.origin").rstrip("/")
    return store


def _normalize_location(
    stores: dict[str, dict[str, Any]], raw: object, field: str
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ResolverError(f"{field} must be an inline table")
    store_name = _name(raw.get("store"), f"{field}.store")
    if store_name not in stores:
        raise ResolverError(f"{field} names unknown store {store_name!r}")
    relation = _required_string(raw.get("relation"), f"{field}.relation")
    if relation not in {"exact", "publication"}:
        raise ResolverError(f"{field}.relation must be 'exact' or 'publication'")
    store = stores[store_name]
    if store["kind"] == "publication" and relation != "publication":
        raise ResolverError(f"{field} cannot claim exact bytes in a publication store")

    has_location = "location" in raw
    has_uri = "uri" in raw
    if has_location == has_uri:
        raise ResolverError(f"{field} requires exactly one of location or uri")
    if has_location:
        if store["kind"] != "directory":
            raise ResolverError(f"{field}.location requires a directory store")
        value = _required_string(raw.get("location"), f"{field}.location")
        uri = _directory_uri(store["origin"], value, f"{field}.location")
        return {
            "store": store_name,
            "relation": relation,
            "location": value,
            "uri": uri,
        }
    if store["kind"] == "directory":
        raise ResolverError(f"{field}.uri is invalid for a directory store")
    return {
        "store": store_name,
        "relation": relation,
        "uri": _absolute_uri(raw.get("uri"), f"{field}.uri"),
    }


def _load_inventory(
    contributor: str,
    stores: dict[str, dict[str, Any]],
    declared_hierarchy: tuple[str, ...],
    path: Path,
) -> list[dict[str, Any]]:
    raw = _load_toml(path, "v2 resource inventory")
    if raw.get("version") != 2:
        raise ResolverError(f"inventory version must be 2: {path}")
    if raw.get("contributor") != contributor:
        raise ResolverError(f"inventory contributor does not match package: {path}")
    hierarchy = _hierarchy(raw.get("hierarchy"), f"inventory hierarchy in {path}")
    if hierarchy != declared_hierarchy:
        raise ResolverError(f"inventory hierarchy does not match descriptor: {path}")
    records = raw.get("resource", [])
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ResolverError(f"inventory resources must be tables: {path}")

    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        label = f"resource[{index}] in {path}"
        target = _target_for(contributor, hierarchy, record)
        if "id" not in target["selector"]:
            raise ResolverError(f"{label}.node_id is required")
        protocol = normalize_protocol_id(record.get("protocol"))
        sha256 = normalize_sha256(record.get("sha256"))
        locations_raw = record.get("locations", [])
        if not isinstance(locations_raw, list):
            raise ResolverError(f"{label}.locations must be a list")
        locations = [
            _normalize_location(stores, location, f"{label}.locations[{location_index}]")
            for location_index, location in enumerate(locations_raw)
        ]
        store_names = [location["store"] for location in locations]
        if len(store_names) != len(set(store_names)):
            raise ResolverError(f"{label} contains duplicate store locations")
        item: dict[str, Any] = {
            "target": target,
            "protocol": protocol,
            "sha256": sha256,
            "locations": locations,
            "inventory": path,
        }
        if "produced_by" in record:
            item["produced_by"] = _name(record["produced_by"], f"{label}.produced_by")
        normalized.append(item)
    return normalized


def load_contributor_v2(config_path: Path, raw: dict[str, Any]) -> dict[str, Any]:
    contributor_raw = raw.get("contributor")
    stores_raw = raw.get("stores")
    inventories_raw = raw.get("inventory")
    if not isinstance(contributor_raw, dict):
        raise ResolverError("contributor protocol requires [contributor]")
    contributor = _name(contributor_raw.get("id"), "contributor.id")
    if not isinstance(stores_raw, dict) or not stores_raw:
        raise ResolverError("v2 contributor protocol requires at least one store")
    if not isinstance(inventories_raw, list) or not inventories_raw:
        raise ResolverError("v2 contributor protocol requires at least one inventory")

    stores: dict[str, dict[str, Any]] = {}
    for raw_name, store in stores_raw.items():
        name = _name(raw_name, "store name")
        stores[name] = _normalize_store(config_path.parent, name, store)

    inventories: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    seen_hierarchies: set[tuple[str, ...]] = set()
    for index, inventory in enumerate(inventories_raw):
        label = f"inventory[{index}]"
        if not isinstance(inventory, dict):
            raise ResolverError(f"{label} must be a table")
        hierarchy = _hierarchy(inventory.get("hierarchy"), f"{label}.hierarchy")
        if hierarchy in seen_hierarchies:
            raise ResolverError(f"duplicate inventory hierarchy: {'/'.join(hierarchy)}")
        seen_hierarchies.add(hierarchy)
        path = _package_path(
            config_path.parent, inventory.get("path"), f"{label}.path"
        )
        inventories.append({"hierarchy": list(hierarchy), "path": path})
        resources.extend(
            _load_inventory(
                contributor, stores, hierarchy, path
            )
        )

    seen_resources: set[tuple[str, tuple[str, ...], str]] = set()
    ids: dict[str, str] = {}
    paths: dict[str, str] = {}
    for resource in resources:
        selector = resource["target"]["selector"]
        contribution = resource["target"]["contribution"]
        node_id = selector["id"]
        rooted_path = selector.get("path")
        identity = (
            node_id,
            tuple(contribution["hierarchy"]),
            contribution["key"],
        )
        if identity in seen_resources:
            raise ResolverError(
                "duplicate v2 resource address: "
                f"{node_id} {'/'.join(identity[1])} {identity[2]}"
            )
        seen_resources.add(identity)
        if rooted_path is not None:
            if node_id in ids and ids[node_id] != rooted_path:
                raise ResolverError("contributor inventories map one id to several paths")
            if rooted_path in paths and paths[rooted_path] != node_id:
                raise ResolverError("contributor inventories map one path to several ids")
            ids[node_id] = rooted_path
            paths[rooted_path] = node_id

    return {
        "version": 2,
        "path": config_path,
        "contributor": contributor,
        "stores": stores,
        "inventories": inventories,
        "resources": resources,
    }


def _location_available(
    package: dict[str, Any], location: dict[str, Any]
) -> bool:
    store = package["stores"][location["store"]]
    if not store["enabled"]:
        return False
    if store["kind"] == "directory":
        return Path(unquote(urlsplit(location["uri"]).path)).exists()
    return True


def validate_contributor_v2(package: dict[str, Any]) -> dict[str, Any]:
    verified = 0
    unavailable = 0
    locations = 0
    for resource in package["resources"]:
        for location in resource["locations"]:
            locations += 1
            if not _location_available(package, location):
                unavailable += 1
                continue
            store = package["stores"][location["store"]]
            if store["kind"] != "directory" or location["relation"] != "exact":
                continue
            path = Path(unquote(urlsplit(location["uri"]).path))
            result = verify_resource_digest(
                path, resource["protocol"], resource["sha256"]
            )
            if not result["valid"]:
                target = resource["target"]
                raise ResolverError(
                    "resource digest mismatch for "
                    f"{target['selector']['id']} "
                    f"{target['contribution']['key']}: "
                    f"expected {result['expected']}, got {result['actual']}"
                )
            verified += 1
    return {
        "version": 2,
        "valid": True,
        "contributor": package["contributor"],
        "hierarchies": len(package["inventories"]),
        "stores": len(package["stores"]),
        "resources": len(package["resources"]),
        "locations": locations,
        "verified_exact_local": verified,
        "unavailable_locations": unavailable,
    }


def inspect_contributor_v2(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 2,
        "contributor": package["contributor"],
        "hierarchies": [
            {"path": item["hierarchy"], "inventory": str(item["path"])}
            for item in package["inventories"]
        ],
        "stores": [
            {"name": name, **store}
            for name, store in sorted(package["stores"].items())
        ],
        "resources": len(package["resources"]),
    }


def _hierarchy_prefix(value: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return value[: len(prefix)] == prefix


def discover_contributor_v2(
    package: dict[str, Any],
    *,
    node_id: str | None = None,
    rooted_path: str | None = None,
    hierarchy: str | list[str] | tuple[str, ...] | None = None,
    resource_key: str | None = None,
    protocol: str | None = None,
    store: str | None = None,
    relation: str | None = None,
) -> dict[str, Any]:
    if store is not None and store not in package["stores"]:
        raise ResolverError(f"unknown contributor store: {store!r}")
    hierarchy_filter = _hierarchy(hierarchy) if hierarchy is not None else None
    if resource_key is not None:
        resource_key = _name(resource_key, "resource key")
    if protocol is not None:
        protocol = normalize_protocol_id(protocol)
    if relation is not None and relation not in {"exact", "publication"}:
        raise ResolverError("relation must be 'exact' or 'publication'")
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

    id_seen = False
    path_seen = False
    pair_seen = False
    discoveries: list[dict[str, Any]] = []
    for resource in package["resources"]:
        target = resource["target"]
        selector = target["selector"]
        contribution = target["contribution"]
        if "id" in query_selector and selector.get("id") == query_selector["id"]:
            id_seen = True
        if "path" in query_selector and selector.get("path") == query_selector["path"]:
            path_seen = True
        if (
            "id" in query_selector
            and "path" in query_selector
            and selector.get("id") == query_selector["id"]
            and selector.get("path") == query_selector["path"]
        ):
            pair_seen = True
        if any(selector.get(key) != value for key, value in query_selector.items()):
            continue
        resource_hierarchy = tuple(contribution["hierarchy"])
        if hierarchy_filter is not None and not _hierarchy_prefix(
            resource_hierarchy, hierarchy_filter
        ):
            continue
        if resource_key is not None and contribution["key"] != resource_key:
            continue
        if protocol is not None and resource["protocol"] != protocol:
            continue
        locations = [
            location
            for location in resource["locations"]
            if _location_available(package, location)
            and (store is None or location["store"] == store)
            and (relation is None or location["relation"] == relation)
        ]
        if (store is not None or relation is not None) and not locations:
            continue
        item = {
            "target": target,
            "protocol": resource["protocol"],
            "sha256": resource["sha256"],
            "stores": [
                {
                    "name": location["store"],
                    "relation": location["relation"],
                    "uri": location["uri"],
                }
                for location in locations
            ],
        }
        if "produced_by" in resource:
            item["produced_by"] = resource["produced_by"]
        discoveries.append(item)

    if (
        "id" in query_selector
        and "path" in query_selector
        and not pair_seen
        and (id_seen or path_seen)
    ):
        raise ResolverError("id and path do not identify the same target")

    discoveries.sort(
        key=lambda item: (
            item["target"]["selector"].get("path", ""),
            item["target"]["selector"]["id"],
            tuple(item["target"]["contribution"]["hierarchy"]),
            item["target"]["contribution"]["key"],
        )
    )
    return {
        "version": 2,
        "contributor": package["contributor"],
        "discoveries": discoveries,
    }


def project_contributor_v2(
    package: dict[str, Any], **filters: Any
) -> dict[str, Any]:
    discoveries = discover_contributor_v2(package, **filters)["discoveries"]
    locations: list[dict[str, Any]] = []
    for discovery in discoveries:
        for store in discovery["stores"]:
            store_spec = package["stores"][store["name"]]
            locations.append(
                {
                    "target": discovery["target"],
                    "protocol": discovery["protocol"],
                    "sha256": discovery["sha256"],
                    "store": {
                        "version": 2,
                        "store": store["name"],
                        "contributor": package["contributor"],
                        "kind": store_spec["kind"],
                        "relation": store["relation"],
                    },
                    "uri": store["uri"],
                }
            )
    return {"version": 2, "locations": locations}


def identify_contributor_v2(
    package: dict[str, Any], uri: str
) -> dict[str, Any]:
    absolute = _absolute_uri(uri, "uri")
    matches: list[dict[str, Any]] = []
    for resource in package["resources"]:
        for location in resource["locations"]:
            if not _location_available(package, location) or location["uri"] != absolute:
                continue
            matches.append(
                {
                    "store": location["store"],
                    "relation": location["relation"],
                    "target": resource["target"],
                    "protocol": resource["protocol"],
                    "sha256": resource["sha256"],
                }
            )
    return {"version": 2, "uri": absolute, "matches": matches}


def compare_k_registry_v2(
    package: dict[str, Any], accepted: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Compare a v2 contributor inventory with normalized accepted K records."""

    inventory = {
        (
            item["target"]["selector"]["id"],
            tuple(item["target"]["contribution"]["hierarchy"]),
            item["target"]["contribution"]["key"],
        ): (item["protocol"], item["sha256"])
        for item in package["resources"]
    }
    registry: dict[tuple[str, tuple[str, ...], str], tuple[str, str]] = {}
    for index, item in enumerate(accepted):
        if not isinstance(item, dict):
            raise ResolverError(f"accepted[{index}] must be an object")
        contributor = _name(item.get("contributor"), f"accepted[{index}].contributor")
        if contributor != package["contributor"]:
            continue
        selector = normalize_selector({"id": item.get("node_id")})
        identity = (
            selector["id"],
            _hierarchy(item.get("hierarchy"), f"accepted[{index}].hierarchy"),
            _name(item.get("key"), f"accepted[{index}].key"),
        )
        if identity in registry:
            raise ResolverError(f"duplicate accepted K record: {identity!r}")
        registry[identity] = (
            normalize_protocol_id(item.get("protocol")),
            normalize_sha256(item.get("sha256")),
        )

    missing = sorted(identity for identity in registry if identity not in inventory)
    unregistered = sorted(identity for identity in inventory if identity not in registry)
    mismatched = sorted(
        identity
        for identity in registry.keys() & inventory.keys()
        if registry[identity] != inventory[identity]
    )
    return {
        "version": 2,
        "valid": not missing and not unregistered and not mismatched,
        "contributor": package["contributor"],
        "missing": [_identity_payload(item) for item in missing],
        "unregistered": [_identity_payload(item) for item in unregistered],
        "mismatched": [_identity_payload(item) for item in mismatched],
    }


def parse_k_contributions_v2(
    node_id: str, raw: object
) -> list[dict[str, Any]]:
    """Normalize one K node's typed c_/h_/r_ contribution mapping."""

    selector = normalize_selector({"id": node_id})
    if not isinstance(raw, dict):
        raise ResolverError("K contributions must be a mapping")
    accepted: list[dict[str, Any]] = []
    for contributor_key, hierarchy_raw in raw.items():
        if not isinstance(contributor_key, str) or not contributor_key.startswith("c_"):
            raise ResolverError("K contributor keys must start with c_")
        contributor = _name(contributor_key[2:], "K contributor key")
        if not isinstance(hierarchy_raw, dict) or not hierarchy_raw:
            raise ResolverError(f"{contributor_key} must contain hierarchy entries")
        _parse_k_hierarchy(
            selector["id"], contributor, (), hierarchy_raw, accepted
        )
    return accepted


def _parse_k_hierarchy(
    node_id: str,
    contributor: str,
    prefix: tuple[str, ...],
    raw: dict[str, Any],
    accepted: list[dict[str, Any]],
) -> None:
    for typed_key, value in raw.items():
        if not isinstance(typed_key, str):
            raise ResolverError("K hierarchy and resource keys must be strings")
        if typed_key.startswith("h_"):
            segment = _name(typed_key[2:], "K hierarchy key")
            if not isinstance(value, dict) or not value:
                raise ResolverError(f"{typed_key} must contain hierarchy or resources")
            _parse_k_hierarchy(
                node_id, contributor, (*prefix, segment), value, accepted
            )
            continue
        if typed_key.startswith("r_"):
            if not prefix:
                raise ResolverError("K resources require at least one h_ segment")
            key = _name(typed_key[2:], "K resource key")
            if not isinstance(value, dict):
                raise ResolverError(f"{typed_key} must map to protocol and sha256")
            unknown = set(value) - {"protocol", "sha256"}
            if unknown:
                raise ResolverError(
                    f"{typed_key} has unsupported fields: {', '.join(sorted(unknown))}"
                )
            accepted.append(
                {
                    "node_id": node_id,
                    "contributor": contributor,
                    "hierarchy": list(prefix),
                    "key": key,
                    "protocol": normalize_protocol_id(value.get("protocol")),
                    "sha256": normalize_sha256(value.get("sha256")),
                }
            )
            continue
        raise ResolverError(f"K overlay key must start with h_ or r_: {typed_key!r}")


def _identity_payload(
    identity: tuple[str, tuple[str, ...], str]
) -> dict[str, Any]:
    return {
        "node_id": identity[0],
        "hierarchy": list(identity[1]),
        "key": identity[2],
    }


def contributor_template_v2(contributor: str, hierarchy: str) -> tuple[str, str, Path]:
    contributor_id = _name(contributor, "contributor id")
    segments = _hierarchy(hierarchy)
    hierarchy_toml = ", ".join(f'"{segment}"' for segment in segments)
    relative = Path("storage", *segments, "resources.toml")
    descriptor = f'''version = 2

[contributor]
id = "{contributor_id}"

[stores.local]
kind = "directory"
enabled = true
origin = "."

[[inventory]]
hierarchy = [{hierarchy_toml}]
path = "{relative.as_posix()}"
'''
    inventory = f'''version = 2
contributor = "{contributor_id}"
hierarchy = [{hierarchy_toml}]
'''
    return descriptor, inventory, relative
