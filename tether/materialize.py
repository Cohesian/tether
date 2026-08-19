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
        target = normalize_target(raw.get("target"))
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
            },
        )
        resource["locations"].append(
            {
                "store": store["store"],
                "uri": uri,
            }
        )

    resources = sorted(
        grouped.values(),
        key=lambda item: (
            item["target"]["selector"].get("path", ""),
            item["target"]["selector"].get("id", ""),
            item["target"]["contribution"]["domain"],
            item["target"]["contribution"]["format"],
        ),
    )
    for resource in resources:
        resource["locations"].sort(key=lambda item: item["store"])
    return {"version": 1, "resources": resources}


def _directory_location(target: dict[str, Any], uri: str) -> PurePosixPath:
    selector = target["selector"]
    stem = selector.get("path") or selector.get("id")
    if stem is None:
        raise ResolverError("directory layout requires a rooted path or id")
    content_format = target["contribution"]["format"]
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
            relative = _directory_location(
                resource["target"], resource["locations"][0]["uri"]
            )
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
            _copy_uri(source["uri"], output)
            manifest_resources.append(
                {
                    "target": resource["target"],
                    "locations": [source],
                    "materialized": {
                        "location": relative.as_posix(),
                        "uri": output.as_uri(),
                    },
                }
            )

    manifest = {
        "version": 1,
        "contributor": package["contributor"],
        "layout": layout,
        "store": store,
        "resources": manifest_resources,
    }
    _write_manifest(manifest_path, manifest, force)
    return {
        "version": 1,
        "contributor": package["contributor"],
        "layout": layout,
        "store": store,
        "destination": str(destination),
        "manifest": str(manifest_path),
        "resources": len(manifest_resources),
    }
