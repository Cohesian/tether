"""Tether: Cohesian's resource-to-store bridge."""

from .resolver import ResolverError, identify, resolve, resolve_discoveries
from .materialize import group_locations, materialize_contributor
from .protocol import (
    check_contributor,
    compare_k_registry,
    discover_contributor,
    identify_contributor,
    inspect_contributor,
    load_contributor,
    parse_k_contributions,
    project_contributor,
    validate_contributor,
)
from .resource_protocols import (
    PROTOCOLS,
    protocol_is_tree,
    protocol_spec,
    protocol_suffix,
    resource_digest,
    resource_members,
    verify_resource_digest,
)

__all__ = [
    "ResolverError",
    "check_contributor",
    "compare_k_registry",
    "discover_contributor",
    "identify",
    "identify_contributor",
    "inspect_contributor",
    "group_locations",
    "load_contributor",
    "materialize_contributor",
    "parse_k_contributions",
    "project_contributor",
    "PROTOCOLS",
    "protocol_is_tree",
    "protocol_spec",
    "protocol_suffix",
    "resource_digest",
    "resource_members",
    "resolve",
    "resolve_discoveries",
    "validate_contributor",
    "verify_resource_digest",
]
__version__ = "0.3.0"
