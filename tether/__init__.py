"""Tether: Cohesian's resource-to-store bridge."""

from .resolver import ResolverError, identify, resolve, resolve_discoveries
from .materialize import group_locations, materialize_contributor
from .protocol import (
    check_contributor,
    discover_contributor,
    identify_contributor,
    inspect_contributor,
    load_contributor,
    project_contributor,
    validate_contributor,
)

__all__ = [
    "ResolverError",
    "check_contributor",
    "discover_contributor",
    "identify",
    "identify_contributor",
    "inspect_contributor",
    "group_locations",
    "load_contributor",
    "materialize_contributor",
    "project_contributor",
    "resolve",
    "resolve_discoveries",
    "validate_contributor",
]
__version__ = "0.2.0"
