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
DIVISION_PATH = "T-math/L-division/E-01-introduction"
CARBON_ID = "2a05068f-d48c-4fdd-915c-778bc8f42211"


class ResearchIntegrationTests(unittest.TestCase):
    def test_research_exposes_a_nonempty_consistent_inventory(self) -> None:
        result = validate_contributor(load_contributor(RESEARCH_PROTOCOL))
        self.assertGreater(result["resources"], 0)
        self.assertGreaterEqual(result["locations"], result["resources"])
        self.assertEqual(result["verified_exact_local"], result["resources"])

    def test_contributor_protocol_discovers_one_real_paper(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        discovery = discover_contributor(
            package,
            node_id=DIVISION_ID,
            hierarchy="documents",
            resource_key="md",
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
            hierarchy="documents",
            resource_key="md",
        )
        expected = (
            RESEARCH_PROTOCOL.parent
            / "storage/documents/local"
            / f"{DIVISION_PATH}.md"
        ).resolve()
        self.assertEqual(result["locations"][0]["uri"], expected.as_uri())

    def test_research_domain_projection_resolves_the_current_corpus(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        result = project_contributor(package, hierarchy="documents")
        self.assertGreater(len(result["locations"]), 0)
        stores = {item["store"]["store"] for item in result["locations"]}
        self.assertTrue({"local", "github"} <= stores)

    def test_studio_produced_scene_is_owned_and_exposed_by_research(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        discovery = discover_contributor(
            package,
            node_id=CARBON_ID,
            hierarchy="media",
            resource_key="loci-project",
        )
        self.assertEqual(len(discovery["discoveries"]), 1)
        item = discovery["discoveries"][0]
        self.assertEqual(item["produced_by"], "studio")
        self.assertEqual(
            {store["name"] for store in item["stores"]},
            {"local", "github"},
        )

    def test_studio_produced_video_has_exact_and_publication_locations(self) -> None:
        package = load_contributor(RESEARCH_PROTOCOL)
        result = project_contributor(
            package,
            node_id=CARBON_ID,
            hierarchy="media",
            resource_key="mp4",
        )
        locations = {
            item["store"]["store"]: (item["store"]["relation"], item["uri"])
            for item in result["locations"]
        }
        self.assertEqual(set(locations), {"local", "youtube"})
        self.assertEqual(locations["local"][0], "exact")
        self.assertEqual(locations["youtube"][0], "publication")
        self.assertTrue(locations["youtube"][1].startswith("https://youtu.be/"))


if __name__ == "__main__":
    unittest.main()
