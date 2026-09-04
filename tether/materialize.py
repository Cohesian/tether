"""Explicit materialization of resolved contributor resources."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

from .protocol import project_contributor
from .protocol_v2 import normalize_v2_target
from .resource_protocols import (
    protocol_is_tree,
    protocol_suffix,
    resource_members,
    verify_resource_digest,
)
from .resolver import ResolverError, normalize_target


MANIFEST_NAME = "tether-manifest.json"


def group_locations(payload: object) -> dict[str, Any]:
    """Group flat resolved locations by logical resource identity."""

    if not isinstance(payload, dict) or not isinstance(payload.get("locations"), list):
        raise ResolverError("resolved payload must contain a locations list")

    grouped: dict[str, dict[str, Any]] = {}
    for raw in payload["locations"]:
        if not isinstance(raw, dict):
            raise ResolverError("each resolved location must be an object")
        raw_target = raw.get("target")
        contribution = raw_target.get("contribution") if isinstance(raw_target, dict) else None
        target = (
            normalize_v2_target(raw_target)
            if isinstance(contribution, dict) and "hierarchy" in contribution
            else normalize_target(raw_target)
        )
        store = raw.get("store")
        uri = raw.get("uri")
        if not isinstance(store, dict) or not isinstance(store.get("store"), str):
            raise ResolverError("each resolved location requires a store")
        if not isinstance(uri, str) or not urlsplit(uri).scheme:
            raise ResolverError("each resolved location requires an absolute URI")
        key = json.dumps(target, sort_keys=True, separators=(",", ":"))
        resource = grouped.setdefault(
            key,
            {
                "target": target,
                "locations": [],
                **(
                    {
                        "protocol": raw["protocol"],
                        "sha256": raw["sha256"],
                    }
                    if "protocol" in raw and "sha256" in raw
                    else {}
                ),
            },
        )
        resource["locations"].append(
            {
                "store": store["store"],
                **(
                    {"relation": store["relation"]}
                    if "relation" in store
                    else {}
                ),
                "uri": uri,
            }
        )

    resources = sorted(
        grouped.values(),
        key=lambda item: (
            item["target"]["selector"].get("path", ""),
            item["target"]["selector"].get("id", ""),
            tuple(item["target"]["contribution"].get("hierarchy", [])),
            item["target"]["contribution"].get(
                "key", item["target"]["contribution"].get("format", "")
            ),
        ),
    )
    for resource in resources:
        resource["locations"].sort(key=lambda item: item["store"])
    return {"version": payload.get("version", 1), "resources": resources}


def _directory_location(resource: dict[str, Any], uri: str) -> PurePosixPath:
    target = resource["target"]
    selector = target["selector"]
    stem = selector.get("path") or selector.get("id")
    if stem is None:
        raise ResolverError("directory layout requires a rooted path or id")
    contribution = target["contribution"]
    if "hierarchy" in contribution:
        key = contribution["key"]
        suffix = protocol_suffix(resource["protocol"])
        leaf = key if suffix is None else f"{key}{suffix}"
        location = PurePosixPath(stem) / leaf
        if location.is_absolute() or any(
            part in {"", ".", ".."} for part in location.parts
        ):
            raise ResolverError("resource cannot be represented safely in dir layout")
        return location
    content_format = contribution["format"]
    parsed = urlsplit(uri)
    source_is_directory = (
        parsed.scheme.lower() == "file"
        and Path(unquote(parsed.path)).is_dir()
    )
    location = PurePosixPath(stem if source_is_directory else f"{stem}.{content_format}")
    if location.is_absolute() or any(
        part in {"", ".", ".."} for part in location.parts
    ):
        raise ResolverError("resource cannot be represented safely in dir layout")
    return location


def _copy_v2_resource(
    uri: str, destination: Path, protocol: str, expected_sha256: str
) -> None:
    if not protocol_is_tree(protocol):
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".verify",
            )
        )
        staged = staging_root / f"resource{protocol_suffix(protocol) or ''}"
        backup_root: Path | None = None
        backup: Path | None = None
        try:
            _copy_uri(uri, staged)
            result = verify_resource_digest(staged, protocol, expected_sha256)
            if not result["valid"]:
                raise ResolverError(
                    "materialized resource digest mismatch: "
                    f"expected {result['expected']}, got {result['actual']}"
                )
            if destination.exists():
                backup_root = Path(
                    tempfile.mkdtemp(
                        dir=destination.parent,
                        prefix=f".{destination.name}.",
                        suffix=".bak",
                    )
                )
                backup = backup_root / "previous"
                os.replace(destination, backup)
            os.replace(staged, destination)
        except OSError as exc:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise ResolverError(f"could not materialize {uri}: {exc}") from exc
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root)
            if backup_root is not None and backup_root.exists():
                shutil.rmtree(backup_root)
        return
    parsed = urlsplit(uri)
    if parsed.scheme.lower() != "file":
        raise ResolverError(
            f"{protocol} cannot materialize from a remote URI without a transfer "
            "protocol; use --layout map"
        )
    source = Path(unquote(parsed.path))
    verification = verify_resource_digest(source, protocol, expected_sha256)
    if not verification["valid"]:
        raise ResolverError(
            "materialized resource digest mismatch: "
            f"expected {verification['expected']}, got {verification['actual']}"
        )
    members = resource_members(source, protocol)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
    )
    backup_root: Path | None = None
    backup: Path | None = None
    try:
        for logical, member in members:
            output = temporary.joinpath(*logical.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(member, output)
        if destination.exists():
            backup_root = Path(
                tempfile.mkdtemp(
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".bak",
                )
            )
            backup = backup_root / "previous"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except OSError as exc:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise ResolverError(f"could not materialize {uri}: {exc}") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root)


def _copy_local_directory(source: Path, destination: Path) -> None:
    try:
        destination.resolve().relative_to(source.resolve())
    except ValueError:
        pass
    else:
        raise ResolverError("directory destination cannot be inside its source")

    temporary = Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
    )
    backup_root: Path | None = None
    backup: Path | None = None
    try:
        shutil.copytree(source, temporary, dirs_exist_ok=True)
        if destination.exists():
            backup_root = Path(
                tempfile.mkdtemp(
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".bak",
                )
            )
            backup = backup_root / "previous"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except OSError as exc:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise ResolverError(f"could not materialize {source.as_uri()}: {exc}") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root)


def _copy_uri(uri: str, destination: Path) -> None:
    scheme = urlsplit(uri).scheme.lower()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if scheme == "file":
        source = Path(unquote(urlsplit(uri).path))
        if source.is_dir():
            _copy_local_directory(source, destination)
            return

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            if scheme == "file":
                source = Path(unquote(urlsplit(uri).path))
                if not source.is_file():
                    raise ResolverError(f"local source does not exist: {source}")
                with source.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
            elif scheme in {"http", "https"}:
                with urlopen(uri) as response:  # noqa: S310 - explicit user store
                    shutil.copyfileobj(response, output)
            else:
                raise ResolverError(
                    f"store URI scheme {scheme!r} cannot materialize as dir; "
                    "use --layout map"
                )
        os.replace(temporary, destination)
        temporary = None
    except OSError as exc:
        raise ResolverError(f"could not materialize {uri}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_manifest(path: Path, payload: dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise ResolverError(f"manifest already exists: {path}; use --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def materialize_contributor(
    package: dict[str, Any],
    destination: Path,
    *,
    layout: str,
    force: bool = False,
    **filters: str | None,
) -> dict[str, Any]:
    """Resolve one store and materialize it as a directory or URI map."""

    store = filters.get("store")
    if not store:
        raise ResolverError("pull requires one explicit store")
    if layout not in {"dir", "map"}:
        raise ResolverError("pull layout must be 'dir' or 'map'")
    store_spec = package["stores"].get(store)
    if store_spec is None:
        raise ResolverError(f"unknown contributor store: {store!r}")
    if (
        layout == "dir"
        and store_spec["kind"] == "remote"
        and package.get("version") == 1
        and store_spec["strategy"] == "map"
    ):
        raise ResolverError(
            "mapped remote stores cannot materialize safely as dir; "
            "use --layout map"
        )

    destination = destination.resolve()
    grouped = group_locations(project_contributor(package, **filters))
    if not grouped["resources"]:
        raise ResolverError("no available resources match the pull query")

    planned: list[tuple[dict[str, Any], Path, PurePosixPath]] = []
    seen: dict[PurePosixPath, dict[str, Any]] = {}
    if layout == "dir":
        for resource in grouped["resources"]:
            if len(resource["locations"]) != 1:
                raise ResolverError("pull selected more than one location per resource")
            source = resource["locations"][0]
            if source.get("relation") == "publication":
                raise ResolverError(
                    "publication locations cannot materialize as exact files; "
                    "use --layout map"
                )
            relative = _directory_location(resource, source["uri"])
            if relative in seen:
                raise ResolverError(
                    f"dir layout collision at {relative}; narrow the domain or format"
                )
            seen[relative] = resource["target"]
            output = destination.joinpath(*relative.parts)
            if output.exists() and not force:
                raise ResolverError(f"destination already exists: {output}; use --force")
            planned.append((resource, output, relative))

    manifest_path = destination / MANIFEST_NAME
    if manifest_path.exists() and not force:
        raise ResolverError(f"manifest already exists: {manifest_path}; use --force")

    manifest_resources: list[dict[str, Any]] = []
    if layout == "map":
        manifest_resources = grouped["resources"]
    else:
        for resource, output, relative in planned:
            source = resource["locations"][0]
            if package.get("version") == 2:
                _copy_v2_resource(
                    source["uri"],
                    output,
                    resource["protocol"],
                    resource["sha256"],
                )
            else:
                _copy_uri(source["uri"], output)
            manifest_resources.append(
                {
                    "target": resource["target"],
                    **(
                        {
                            "protocol": resource["protocol"],
                            "sha256": resource["sha256"],
                        }
                        if package.get("version") == 2
                        else {}
                    ),
                    "locations": [source],
                    "materialized": {
                        "location": relative.as_posix(),
                        "uri": output.as_uri(),
                    },
                }
            )

    manifest = {
        "version": package.get("version", 1),
        "contributor": package["contributor"],
        "layout": layout,
        "store": store,
        "resources": manifest_resources,
    }
    _write_manifest(manifest_path, manifest, force)
    return {
        "version": package.get("version", 1),
        "contributor": package["contributor"],
        "layout": layout,
        "store": store,
        "destination": str(destination),
        "manifest": str(manifest_path),
        "resources": len(manifest_resources),
    }
