from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORIES_ROOT = Path(__file__).resolve().parents[2]
STUDIO_PROTOCOL = REPOSITORIES_ROOT / "studio" / "contributor.toml"

from tether import (  # noqa: E402
    discover_contributor,
    identify_contributor,
    load_contributor,
    project_contributor,
    validate_contributor,
)


CARBON_ID = "2a05068f-d48c-4fdd-915c-778bc8f42211"
CARBON_PATH = "T-computer-science/L-composite/F-01-carbon-binder"


class StudioIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = load_contributor(STUDIO_PROTOCOL)

    def test_studio_identifies_itself_and_eight_resources(self) -> None:
        result = validate_contributor(self.package)
        self.assertEqual(result["contributor"], "studio")
        self.assertEqual(result["domains"], 2)
        self.assertEqual(result["resources"], 8)

    def test_scene_is_available_locally_and_on_github(self) -> None:
        result = discover_contributor(
            self.package,
            node_id=CARBON_ID,
            domain="scenes",
            content_format="loci-project",
        )
        stores = {
            item["name"] for item in result["discoveries"][0]["stores"]
        }
        self.assertEqual(stores, {"local-scenes", "github"})

    def test_existing_video_is_available_locally_and_on_youtube(self) -> None:
        result = project_contributor(
            self.package,
            node_id=CARBON_ID,
            domain="videos",
            content_format="mp4",
        )
        locations = {
            item["store"]["store"]: item["uri"] for item in result["locations"]
        }
        self.assertEqual(set(locations), {"local-videos", "youtube"})
        self.assertTrue(locations["local-videos"].endswith("F-01-carbon-binder.mp4"))
        self.assertTrue(locations["youtube"].startswith("https://youtu.be/"))

    def test_local_scene_uri_identifies_the_k_resource(self) -> None:
        uri = (
            STUDIO_PROTOCOL.parent
            / "storage/k-graph/scenes/local"
            / CARBON_PATH
        ).resolve().as_uri()
        result = identify_contributor(self.package, uri)
        target = result["matches"][0]["target"]
        self.assertEqual(target["selector"]["id"], CARBON_ID)
        self.assertEqual(target["contribution"]["domain"], "scenes")
        self.assertEqual(target["contribution"]["format"], "loci-project")


if __name__ == "__main__":
    unittest.main()
