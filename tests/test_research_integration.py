from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORIES_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_PROTOCOL = REPOSITORIES_ROOT / "research" / "contributor.toml"

from tether import (  # noqa: E402
    discover_contributor,
    load_contributor,
    project_contributor,
    validate_contributor,
)


DIVISION_ID = "ff647a5d-44f0-42af-9f01-abcadd04fb37"
DIVISION_PATH = "T-math/L-division/F-01-introduction"


class ResearchIntegrationTests(unittest.TestCase):
    def test_research_has_25_logical_resources(self) -> None:
        result = validate_contributor(load_contributor(RESEARCH_PROTOCOL))
        self.assertEqual(result["routes"], 50)
        self.assertEqual(result["resources"], 25)

    def test_contributor_protocol_discovers_one_real_paper(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        discovery = discover_contributor(
            package,
            node_id=DIVISION_ID,
            content_format="md",
        )
        self.assertEqual(len(discovery["discoveries"]), 1)
        self.assertEqual(
            discovery["discoveries"][0]["stores"][0]["name"], "local"
        )

    def test_contributor_protocol_resolves_one_real_paper(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        result = project_contributor(
            package,
            node_id=DIVISION_ID,
            content_format="md",
        )
        expected = (
            RESEARCH_PROTOCOL.parent
            / "storage/documents/local"
            / f"{DIVISION_PATH}.md"
        ).resolve()
        self.assertEqual(result["locations"][0]["uri"], expected.as_uri())

    def test_research_domain_projection_resolves_the_current_corpus(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        result = project_contributor(package, domain="documents")
        self.assertEqual(len(result["locations"]), 50)
        self.assertEqual(
            {item["store"]["store"] for item in result["locations"]},
            {"local", "github"},
        )


if __name__ == "__main__":
    unittest.main()
