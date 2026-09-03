"""Command-line interface for the Tether resource-to-store bridge."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Sequence

from .materialize import group_locations, materialize_contributor
from .resolver import (
    ResolverError,
    identify,
    load_document,
    resolve,
    resolve_discoveries,
)
from .resource_protocols import resource_digest, verify_resource_digest
from .protocol import (
    check_contributor,
    contributor_template,
    discover_contributor,
    identify_contributor,
    inspect_contributor,
    load_contributor,
    project_contributor,
    contributor_template_v2,
    validate_contributor,
)


def _add_contributor_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contributor", type=Path, required=True)


def _add_contributor_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("contributor", type=Path, help="contributor directory or TOML")


def _add_filters(
    parser: argparse.ArgumentParser, *, store_required: bool = False
) -> None:
    parser.add_argument("--id", dest="node_id")
    parser.add_argument("--path", dest="rooted_path")
    parser.add_argument("--domain")
    parser.add_argument("--format", dest="content_format")
    parser.add_argument(
        "--hierarchy",
        help="v2 hierarchy prefix, written as documents or media/videos",
    )
    parser.add_argument("--key", dest="resource_key", help="v2 resource key")
    parser.add_argument("--protocol", help="v2 resource protocol id")
    parser.add_argument(
        "--relation", choices=("exact", "publication"), help="v2 location relation"
    )
    parser.add_argument("--store", required=store_required)


def _add_output(parser: argparse.ArgumentParser, default: str = "table") -> None:
    parser.add_argument(
        "--output",
        choices=("table", "json", "tree"),
        default=default,
        help="response projection (default: %(default)s)",
    )


def _filters(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "node_id": args.node_id,
        "rooted_path": args.rooted_path,
        "domain": args.domain,
        "content_format": args.content_format,
        "hierarchy": args.hierarchy,
        "resource_key": args.resource_key,
        "protocol": args.protocol,
        "relation": args.relation,
        "store": args.store,
    }


def _resource_listing(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": payload.get("version", 1),
        "contributor": payload["contributor"],
        "resources": [
            {
                "target": item["target"],
                "stores": sorted(store["name"] for store in item["stores"]),
                **(
                    {
                        "protocol": item["protocol"],
                        "sha256": item["sha256"],
                    }
                    if "protocol" in item
                    else {}
                ),
            }
            for item in payload["discoveries"]
        ],
    }


def _print_rows(headers: list[str], rows: list[list[object]]) -> None:
    rendered = [[str(value) for value in row] for row in rows]
    widths = [len(value) for value in headers]
    for row in rendered:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    print("  ".join(value.ljust(width) for value, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rendered:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))


def _resource_rows(payload: dict[str, Any]) -> list[list[object]]:
    rows: list[list[object]] = []
    for resource in payload.get("resources", []):
        target = resource["target"]
        selector = target["selector"]
        contribution = target["contribution"]
        is_v2 = "hierarchy" in contribution
        category = (
            "/".join(contribution["hierarchy"])
            if is_v2
            else contribution["domain"]
        )
        resource_key = (
            contribution["key"] if is_v2 else contribution["format"]
        )
        locations = resource.get("locations")
        if locations is None:
            stores = resource.get("stores", []) or [""]
            locations = [{"store": store, "uri": ""} for store in stores]
        for location in locations or [{"store": "", "uri": ""}]:
            row: list[object] = [
                selector.get("path", selector.get("id", "")),
                category,
                resource_key,
            ]
            if is_v2:
                row.append(resource.get("protocol", ""))
            row.append(location.get("store", ""))
            if is_v2:
                row.append(location.get("relation", ""))
            row.append(location.get("uri", ""))
            rows.append(row)
    return rows


def _emit_table(payload: dict[str, Any]) -> None:
    if isinstance(payload.get("resources"), list):
        print(f"Contributor: {payload.get('contributor', '-')}")
        headers = (
            ["K PATH / ID", "HIERARCHY", "RESOURCE", "PROTOCOL", "STORE", "RELATION", "URI"]
            if payload.get("version") == 2
            else ["K PATH / ID", "DOMAIN", "FORMAT", "STORE", "URI"]
        )
        _print_rows(headers, _resource_rows(payload))
        return
    if (
        payload.get("version") == 2
        and isinstance(payload.get("hierarchies"), list)
        and isinstance(payload.get("stores"), list)
    ):
        print(f"Contributor: {payload['contributor']}")
        print("\nHierarchies")
        _print_rows(
            ["HIERARCHY", "INVENTORY"],
            [
                ["/".join(item["path"]), item["inventory"]]
                for item in payload["hierarchies"]
            ],
        )
        print("\nStores")
        _print_rows(
            ["STORE", "KIND", "ENABLED"],
            [
                [item["name"], item["kind"], item["enabled"]]
                for item in payload["stores"]
            ],
        )
        print(f"\nResources: {payload['resources']}")
        return
    if all(isinstance(payload.get(key), list) for key in ("domains", "stores", "bindings")):
        print(f"Contributor: {payload['contributor']}")
        print("\nDomains")
        _print_rows(
            ["DOMAIN", "FORMATS"],
            [[item["name"], ", ".join(item["formats"])] for item in payload["domains"]],
        )
        print("\nStores")
        _print_rows(
            ["STORE", "KIND", "ENABLED", "STRATEGY"],
            [
                [item["name"], item["kind"], item["enabled"], item["strategy"]]
                for item in payload["stores"]
            ],
        )
        return
    if "stores" in payload and isinstance(payload["stores"], list):
        print(f"Contributor: {payload.get('contributor', '-')}")
        _print_rows(
            ["STORE", "KIND", "ENABLED", "STRATEGY"],
            [
                [item["name"], item["kind"], item["enabled"], item["strategy"]]
                for item in payload["stores"]
            ],
        )
        return
    if "matches" in payload:
        rows = []
        for match in payload["matches"]:
            target = match["target"]
            rows.append(
                [
                    target["selector"].get("path", target["selector"].get("id", "")),
                    target["contribution"]["domain"],
                    target["contribution"]["format"],
                    match["store"],
                ]
            )
        _print_rows(["K PATH / ID", "DOMAIN", "FORMAT", "STORE"], rows)
        return
    _print_rows(
        ["FIELD", "VALUE"],
        [
            [key, json.dumps(value) if isinstance(value, (dict, list)) else value]
            for key, value in payload.items()
        ],
    )


def _emit_tree(payload: dict[str, Any]) -> None:
    resources = payload.get("resources")
    if not isinstance(resources, list):
        _emit_table(payload)
        return
    print(payload.get("contributor", "resources"))
    for resource in resources:
        target = resource["target"]
        selector = target["selector"]
        contribution = target["contribution"]
        print(f"└─ {selector.get('path', selector.get('id', '?'))}")
        if "hierarchy" in contribution:
            branch = "/".join([*contribution["hierarchy"], contribution["key"]])
            protocol = resource.get("protocol", "")
            print(f"   └─ {branch} [{protocol}]")
        else:
            print(f"   └─ {contribution['domain']}/{contribution['format']}")
        locations = resource.get("locations")
        if locations is not None:
            for location in locations:
                relation = location.get("relation")
                suffix = f" ({relation})" if relation else ""
                print(f"      └─ {location['store']}{suffix}: {location['uri']}")
        else:
            for store in resource.get("stores", []):
                print(f"      └─ {store}")


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif output == "tree":
        _emit_tree(payload)
    else:
        _emit_table(payload)


def _initialize_contributor(
    path: Path,
    contributor_id: str,
    domain: str | None,
    formats: list[str] | None,
    *,
    protocol_version: int,
    hierarchy: str | None,
) -> dict[str, Any]:
    root = path.resolve()
    if root.exists() and not root.is_dir():
        raise ResolverError(f"contributor path is not a directory: {root}")
    protocol = root / "contributor.toml"
    if protocol_version == 1:
        if domain is None or not formats:
            raise ResolverError("protocol v1 init requires --domain and --format")
        protocol_text = contributor_template(contributor_id, domain, formats)
        inventory = root / "storage/local/routes.toml"
        inventory_text = "version = 1\n"
    else:
        if hierarchy is None:
            raise ResolverError("protocol v2 init requires --hierarchy")
        if domain is not None or formats:
            raise ResolverError(
                "protocol v2 init uses --hierarchy; --domain and --format are v1 options"
            )
        protocol_text, inventory_text, inventory_relative = contributor_template_v2(
            contributor_id, hierarchy
        )
        inventory = root / inventory_relative
    conflicts = [candidate for candidate in (protocol, inventory) if candidate.exists()]
    if conflicts:
        raise ResolverError(f"contributor scaffold already exists: {conflicts[0]}")
    inventory.parent.mkdir(parents=True, exist_ok=True)
    protocol.write_text(protocol_text, encoding="utf-8")
    inventory.write_text(inventory_text, encoding="utf-8")
    return {
        "version": protocol_version,
        "contributor": contributor_id,
        "path": str(root),
        "protocol": str(protocol),
        "inventory": str(inventory),
    }


def _add_grouped_commands(commands: argparse._SubParsersAction[Any]) -> None:
    contributor = commands.add_parser(
        "contributor", help="create, inspect, and check contributor packages"
    )
    contributor_commands = contributor.add_subparsers(
        dest="contributor_command", required=True
    )

    initializing = contributor_commands.add_parser(
        "init", help="create a contributor package scaffold"
    )
    _add_contributor_path(initializing)
    initializing.add_argument("--id", dest="contributor_id", required=True)
    initializing.add_argument("--protocol-version", type=int, choices=(1, 2), default=2)
    initializing.add_argument("--hierarchy")
    initializing.add_argument("--domain")
    initializing.add_argument("--format", dest="formats", action="append")
    _add_output(initializing)

    showing = contributor_commands.add_parser(
        "show", help="show contributor identity and declared axes"
    )
    _add_contributor_path(showing)
    _add_output(showing)

    checking = contributor_commands.add_parser(
        "check", help="check protocol compatibility and package validity"
    )
    _add_contributor_path(checking)
    _add_output(checking)

    resource = commands.add_parser(
        "resource", help="list, resolve, and identify logical resources"
    )
    resource_commands = resource.add_subparsers(dest="resource_command", required=True)

    listing = resource_commands.add_parser(
        "list", help="list matching resources and available stores"
    )
    _add_contributor_path(listing)
    _add_filters(listing)
    _add_output(listing)

    resolving = resource_commands.add_parser(
        "resolve", help="resolve matching resources to store URIs"
    )
    _add_contributor_path(resolving)
    _add_filters(resolving)
    _add_output(resolving)

    identifying = resource_commands.add_parser(
        "identify", help="identify a logical resource from one URI"
    )
    _add_contributor_path(identifying)
    identifying.add_argument("--uri", required=True)
    _add_output(identifying)

    digesting = resource_commands.add_parser(
        "digest", help="calculate one local resource's protocol-defined SHA-256"
    )
    digesting.add_argument("location", type=Path)
    digesting.add_argument("--protocol", required=True)
    _add_output(digesting)

    verifying = resource_commands.add_parser(
        "verify", help="compare one local resource with an accepted SHA-256"
    )
    verifying.add_argument("location", type=Path)
    verifying.add_argument("--protocol", required=True)
    verifying.add_argument("--sha256", required=True)
    _add_output(verifying)

    store = commands.add_parser("store", help="inspect contributor stores")
    store_commands = store.add_subparsers(dest="store_command", required=True)
    store_listing = store_commands.add_parser("list", help="list declared stores")
    _add_contributor_path(store_listing)
    _add_output(store_listing)

    pulling = commands.add_parser(
        "pull", help="materialize one store as a directory or URI map"
    )
    _add_contributor_path(pulling)
    _add_filters(pulling, store_required=True)
    pulling.add_argument("--into", type=Path, required=True)
    pulling.add_argument("--layout", choices=("dir", "map"), required=True)
    pulling.add_argument("--force", action="store_true")
    _add_output(pulling)

    shell = commands.add_parser("shell", help="open a contributor-scoped session")
    _add_contributor_path(shell)


def _add_legacy_commands(commands: argparse._SubParsersAction[Any]) -> None:
    initializing = commands.add_parser("init", help="legacy contributor scaffold")
    initializing.add_argument("--id", dest="contributor_id", required=True)
    initializing.add_argument("--domain", required=True)
    initializing.add_argument("--format", dest="formats", action="append", required=True)
    initializing.add_argument("--output", type=Path)

    validating = commands.add_parser("validate", help="legacy package validation")
    _add_contributor_option(validating)

    inspecting = commands.add_parser("inspect", help="legacy package inspection")
    _add_contributor_option(inspecting)

    discovering = commands.add_parser("discover", help="legacy resource discovery")
    _add_contributor_option(discovering)
    _add_filters(discovering)

    projecting = commands.add_parser("project", help="legacy URI projection")
    _add_contributor_option(projecting)
    _add_filters(projecting)

    resolving = commands.add_parser("resolve", help="resolve one explicit target")
    resolving.add_argument("--target", type=Path, required=True)
    resolving.add_argument("--descriptor", type=Path, required=True)

    batch = commands.add_parser("resolve-many", help="resolve discovery JSON")
    batch.add_argument("--input", type=Path, help="omit to read standard input")

    identifying = commands.add_parser("identify", help="legacy URI identification")
    identifying.add_argument("--uri", required=True)
    identity_source = identifying.add_mutually_exclusive_group(required=True)
    identity_source.add_argument("--descriptor", type=Path)
    identity_source.add_argument("--contributor", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge Cohesian K resource targets and contributor stores"
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{contributor,resource,store,pull,shell}",
    )
    _add_grouped_commands(commands)
    _add_legacy_commands(commands)
    public = {"contributor", "resource", "store", "pull", "shell"}
    commands._choices_actions[:] = [
        action for action in commands._choices_actions if action.dest in public
    ]
    return parser


def _run_shell(contributor: Path) -> int:
    package = load_contributor(contributor)
    prefix = package["contributor"]
    print(f"Tether contributor session: {prefix}. Type 'help' or 'exit'.")
    aliases = {
        "show": ["contributor", "show"],
        "check": ["contributor", "check"],
        "stores": ["store", "list"],
        "resources": ["resource", "list"],
        "resolve": ["resource", "resolve"],
        "identify": ["resource", "identify"],
        "pull": ["pull"],
    }
    while True:
        try:
            raw = input(f"tether/{prefix}> ").strip()
        except EOFError:
            print()
            return 0
        if not raw:
            continue
        if raw in {"exit", "quit"}:
            return 0
        if raw == "help":
            print("show | check | stores | resources | resolve | identify | pull | exit")
            continue
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            continue
        base = aliases.get(parts[0])
        if base is None:
            print(f"error: unknown session command: {parts[0]}", file=sys.stderr)
            continue
        nested = [*base, str(contributor), *parts[1:]]
        main(nested)


def _run_grouped(args: argparse.Namespace) -> tuple[dict[str, Any] | None, int]:
    if args.command == "contributor":
        if args.contributor_command == "init":
            return (
                _initialize_contributor(
                    args.contributor,
                    args.contributor_id,
                    args.domain,
                    args.formats,
                    protocol_version=args.protocol_version,
                    hierarchy=args.hierarchy,
                ),
                0,
            )
        if args.contributor_command == "show":
            return inspect_contributor(load_contributor(args.contributor)), 0
        result = check_contributor(args.contributor)
        return result, 0 if result["compatibility"] == "compatible" else 1

    if args.command == "resource":
        if args.resource_command == "digest":
            return {
                "version": 2,
                "location": str(args.location.resolve()),
                "protocol": args.protocol,
                "sha256": resource_digest(args.location, args.protocol),
            }, 0
        if args.resource_command == "verify":
            result = verify_resource_digest(
                args.location, args.protocol, args.sha256
            )
            return {
                "version": 2,
                "location": str(args.location.resolve()),
                **result,
            }, 0 if result["valid"] else 1
        package = load_contributor(args.contributor)
        if args.resource_command == "list":
            return _resource_listing(discover_contributor(package, **_filters(args))), 0
        if args.resource_command == "resolve":
            payload = group_locations(project_contributor(package, **_filters(args)))
            payload["contributor"] = package["contributor"]
            return payload, 0
        return identify_contributor(package, args.uri), 0

    if args.command == "store":
        inspected = inspect_contributor(load_contributor(args.contributor))
        return {
            "version": inspected.get("version", 1),
            "contributor": inspected["contributor"],
            "stores": inspected["stores"],
        }, 0

    if args.command == "pull":
        return (
            materialize_contributor(
                load_contributor(args.contributor),
                args.into,
                layout=args.layout,
                force=args.force,
                **_filters(args),
            ),
            0,
        )

    if args.command == "shell":
        return None, _run_shell(args.contributor)
    raise ResolverError(f"unknown grouped command: {args.command}")


def _run_legacy(args: argparse.Namespace) -> dict[str, Any] | str:
    if args.command == "init":
        output = contributor_template(args.contributor_id, args.domain, args.formats)
        if args.output is None:
            return output
        if args.output.exists():
            raise ResolverError(f"output already exists: {args.output}")
        args.output.write_text(output, encoding="utf-8")
        return str(args.output)
    if args.command == "validate":
        return validate_contributor(load_contributor(args.contributor))
    if args.command == "inspect":
        return inspect_contributor(load_contributor(args.contributor))
    if args.command == "discover":
        return discover_contributor(load_contributor(args.contributor), **_filters(args))
    if args.command == "project":
        return project_contributor(load_contributor(args.contributor), **_filters(args))
    if args.command == "resolve":
        return resolve(load_document(args.target), load_document(args.descriptor))
    if args.command == "resolve-many":
        return resolve_discoveries(load_document(args.input))
    if args.contributor is not None:
        return identify_contributor(load_contributor(args.contributor), args.uri)
    return {
        "version": 1,
        "uri": args.uri,
        "targets": identify(args.uri, load_document(args.descriptor)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"contributor", "resource", "store", "pull", "shell"}:
            payload, status = _run_grouped(args)
            if payload is not None:
                _emit(payload, args.output)
            return status

        payload = _run_legacy(args)
        if isinstance(payload, str):
            print(payload, end="" if args.command == "init" and args.output is None else "\n")
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except ResolverError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
