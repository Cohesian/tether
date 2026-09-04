"""Versioned resource shapes and deterministic SHA-256 calculations."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .resolver import ResolverError


SHA256_RE = re.compile(r"[0-9a-f]{64}")
PROTOCOL_ID_RE = re.compile(r"[a-z][a-z0-9-]*@[1-9][0-9]*")

PROTOCOLS: dict[str, dict[str, Any]] = {
    "markdown-file@1": {
        "shape": "file",
        "suffix": ".md",
        "media_type": "text/markdown",
    },
    "markdown-bundle@1": {
        "shape": "markdown-bundle",
        "suffix": None,
        "media_type": "text/markdown",
    },
    "jupyter-notebook-file@1": {
        "shape": "file",
        "suffix": ".ipynb",
        "media_type": "application/x-ipynb+json",
    },
    "mp4-file@1": {
        "shape": "file",
        "suffix": ".mp4",
        "media_type": "video/mp4",
    },
    "python-project@1": {
        "shape": "tree",
        "suffix": None,
        "required": ("pyproject.toml",),
        "excluded_roots": (
            ".pixi",
            ".cache",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".nox",
            ".ipynb_checkpoints",
            "outputs",
            "dist",
            "build",
        ),
        "media_type": "application/vnd.cohesian.python-project",
    },
    "loci-project@1": {
        "shape": "tree",
        "suffix": None,
        "required": ("pyproject.toml", "loci.toml", "scene.toml"),
        "excluded_roots": ("media",),
        "media_type": "application/vnd.cohesian.loci-project",
    },
}

_IGNORED_NAMES = {".DS_Store"}
_IGNORED_PARTS = {".git", ".venv", "__pycache__"}


def normalize_protocol_id(raw: object) -> str:
    if not isinstance(raw, str) or PROTOCOL_ID_RE.fullmatch(raw) is None:
        raise ResolverError(
            "resource protocol must match <name>@<positive-integer-version>"
        )
    if raw not in PROTOCOLS:
        raise ResolverError(f"unsupported resource protocol: {raw!r}")
    return raw


def normalize_sha256(raw: object) -> str:
    if not isinstance(raw, str) or SHA256_RE.fullmatch(raw) is None:
        raise ResolverError("resource sha256 must be 64 lowercase hexadecimal digits")
    return raw


def protocol_spec(protocol_id: object) -> dict[str, Any]:
    return dict(PROTOCOLS[normalize_protocol_id(protocol_id)])


def protocol_suffix(protocol_id: object) -> str | None:
    return protocol_spec(protocol_id)["suffix"]


def protocol_is_tree(protocol_id: object) -> bool:
    return protocol_spec(protocol_id)["shape"] != "file"


def _reject_secret_or_link(path: Path, logical: PurePosixPath) -> None:
    if path.is_symlink():
        raise ResolverError(f"resource member cannot be a symbolic link: {logical}")
    if ".env" in logical.parts:
        raise ResolverError(f"resource member cannot include .env: {logical}")


def _ignored(logical: PurePosixPath, excluded_roots: set[str]) -> bool:
    if logical.name in _IGNORED_NAMES or logical.suffix == ".pyc":
        return True
    if any(part in _IGNORED_PARTS for part in logical.parts):
        return True
    return bool(logical.parts and logical.parts[0] in excluded_roots)


def _tree_members(
    root: Path, *, excluded_roots: Iterable[str] = ()
) -> list[tuple[PurePosixPath, Path]]:
    if not root.is_dir():
        raise ResolverError(f"resource root is not a directory: {root}")
    excluded = set(excluded_roots)
    members: list[tuple[PurePosixPath, Path]] = []
    for path in root.rglob("*"):
        logical = PurePosixPath(path.relative_to(root).as_posix())
        if _ignored(logical, excluded):
            continue
        _reject_secret_or_link(path, logical)
        if path.is_dir():
            continue
        if not path.is_file():
            raise ResolverError(f"unsupported resource member: {logical}")
        members.append((logical, path))
    return members


def resource_members(
    location: Path, protocol_id: object
) -> list[tuple[PurePosixPath, Path]]:
    """Return the protocol-relative members of one local exact resource."""

    protocol = normalize_protocol_id(protocol_id)
    spec = PROTOCOLS[protocol]
    location = location.resolve()

    if spec["shape"] == "file":
        if location.is_symlink() or not location.is_file():
            raise ResolverError(f"resource is not a regular file: {location}")
        expected_suffix = spec["suffix"]
        if location.suffix.lower() != expected_suffix:
            raise ResolverError(
                f"{protocol} requires a {expected_suffix} file: {location}"
            )
        if protocol == "markdown-file@1":
            try:
                location.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ResolverError(f"Markdown resource is not UTE-8: {location}") from exc
        return [(PurePosixPath(f"resource{expected_suffix}"), location)]

    if spec["shape"] == "markdown-bundle":
        if location.is_symlink() or not location.is_file():
            raise ResolverError(f"Markdown entrypoint is not a regular file: {location}")
        if location.suffix.lower() != ".md":
            raise ResolverError(f"markdown-bundle@1 requires a .md entrypoint: {location}")
        try:
            location.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ResolverError(f"Markdown entrypoint is not UTE-8: {location}") from exc
        members = [(PurePosixPath("document.md"), location)]
        companion = location.with_suffix("")
        if companion.exists():
            if not companion.is_dir() or companion.is_symlink():
                raise ResolverError(
                    "markdown-bundle@1 companion must be a real directory: "
                    f"{companion}"
                )
            members.extend(
                (PurePosixPath("assets") / logical, path)
                for logical, path in _tree_members(companion)
            )
        return members

    required = tuple(spec.get("required", ()))
    if not location.is_dir() or location.is_symlink():
        raise ResolverError(f"{protocol} requires a project directory: {location}")
    missing = [name for name in required if not (location / name).is_file()]
    if missing:
        raise ResolverError(
            f"{protocol} is missing required members: {', '.join(missing)}"
        )
    return _tree_members(
        location, excluded_roots=set(spec.get("excluded_roots", ()))
    )


def _normalized_logical_path(path: PurePosixPath) -> str:
    value = unicodedata.normalize("NFC", path.as_posix())
    normalized = PurePosixPath(value)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise ResolverError(f"invalid canonical resource path: {value!r}")
    return normalized.as_posix()


def resource_digest(location: Path, protocol_id: object) -> str:
    """Calculate the canonical SHA-256 digest for one local resource."""

    protocol = normalize_protocol_id(protocol_id)
    members = resource_members(location, protocol)
    if PROTOCOLS[protocol]["shape"] == "file":
        return hashlib.sha256(members[0][1].read_bytes()).hexdigest()

    records: list[tuple[bytes, bytes]] = []
    seen_paths: set[bytes] = set()
    for logical, path in members:
        logical_bytes = _normalized_logical_path(logical).encode("utf-8")
        if logical_bytes in seen_paths:
            raise ResolverError(
                f"resource contains colliding canonical paths: {logical.as_posix()}"
            )
        seen_paths.add(logical_bytes)
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest().encode("ascii")
        record = (
            logical_bytes
            + b"\0"
            + str(len(content)).encode("ascii")
            + b"\0"
            + digest
            + b"\n"
        )
        records.append((logical_bytes, record))
    manifest = b"".join(record for _, record in sorted(records))
    return hashlib.sha256(manifest).hexdigest()


def verify_resource_digest(
    location: Path, protocol_id: object, expected_sha256: object
) -> dict[str, Any]:
    protocol = normalize_protocol_id(protocol_id)
    expected = normalize_sha256(expected_sha256)
    actual = resource_digest(location, protocol)
    return {
        "protocol": protocol,
        "expected": expected,
        "actual": actual,
        "valid": actual == expected,
    }
