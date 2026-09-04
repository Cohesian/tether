from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tether import (
    ResolverError,
    discover_contributor,
    identify_contributor,
    inspect_contributor,
    load_contributor,
    project_contributor,
    validate_contributor,
)
from tether.protocol import contributor_template


NODE_ID = "11111111-1111-4111-8111-111111111111"
NODE_PATH = "T-test/L-example/E-01-paper"


class ContributorProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "storage/local/T-test/L-example").mkdir(parents=True)
        (self.root / "storage/drive").mkdir(parents=True)
        self.paper = self.root / f"storage/local/{NODE_PATH}.md"
        self.paper.write_text("# Paper\n", encoding="utf-8")
        (self.root / "storage/local/routes.toml").write_text(
            f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "md"
location = "{NODE_PATH}.md"
''',
            encoding="utf-8",
        )
        (self.root / "storage/drive/routes.toml").write_text(
            f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "md"
uri = "https://drive.google.com/file/d/example/view"
''',
            encoding="utf-8",
        )
        self.protocol = self.root / "contributor.toml"
        self.protocol.write_text(
            '''version = 1

[contributor]
id = "research"

[domains.documents]
formats = ["md", "ipynb"]

[stores.local]
kind = "directory"
enabled = true
strategy = "template"
origin = "storage/local"

[stores.drive]
kind = "remote"
enabled = true
strategy = "map"

[[bindings]]
domain = "documents"
store = "local"
formats = ["md", "ipynb"]
inventory = "storage/local/routes.toml"
pattern = "{path}.{format}"

[[bindings]]
domain = "documents"
store = "drive"
formats = ["md"]
inventory = "storage/drive/routes.toml"
''',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_inspect_preserves_independent_axes_and_bindings(self) -> None:
        result = inspect_contributor(load_contributor(self.protocol))
        self.assertEqual(result["contributor"], "research")
        self.assertEqual([item["name"] for item in result["domains"]], ["documents"])
        self.assertEqual(
            {item["name"] for item in result["stores"]}, {"local", "drive"}
        )
        self.assertEqual(len(result["bindings"]), 2)

    def test_package_directory_resolves_contributor_toml(self) -> None:
        package = load_contributor(self.root)
        self.assertEqual(package["contributor"], "research")

    def test_validation_reads_every_binding_inventory(self) -> None:
        result = validate_contributor(load_contributor(self.protocol))
        self.assertTrue(result["valid"])
        self.assertEqual(result["bindings"], 2)
        self.assertEqual(result["routes"], 2)
        self.assertEqual(result["resources"], 1)

    def test_discovery_projects_stores_for_one_target(self) -> None:
        package = load_contributor(self.protocol)
        result = discover_contributor(package, rooted_path=NODE_PATH)
        self.assertEqual(len(result["discoveries"]), 1)
        self.assertEqual(
            {item["name"] for item in result["discoveries"][0]["stores"]},
            {"local", "drive"},
        )

    def test_domain_and_store_are_independent_filters(self) -> None:
        package = load_contributor(self.protocol)
        result = discover_contributor(
            package, domain="documents", store="drive", content_format="md"
        )
        stores = result["discoveries"][0]["stores"]
        self.assertEqual([item["name"] for item in stores], ["drive"])

    def test_project_resolves_template_and_map_stores(self) -> None:
        result = project_contributor(load_contributor(self.protocol))
        self.assertEqual(
            {item["uri"] for item in result["locations"]},
            {
                self.paper.resolve().as_uri(),
                "https://drive.google.com/file/d/example/view",
            },
        )

    def test_identify_searches_the_contributor_package(self) -> None:
        result = identify_contributor(
            load_contributor(self.protocol), self.paper.resolve().as_uri()
        )
        self.assertEqual(result["matches"][0]["store"], "local")
        self.assertEqual(
            result["matches"][0]["target"]["selector"]["path"], NODE_PATH
        )
        self.assertEqual(
            result["matches"][0]["target"]["selector"]["id"], NODE_ID
        )

    def test_identify_does_not_invent_an_unlisted_target(self) -> None:
        result = identify_contributor(
            load_contributor(self.protocol),
            (self.root / "storage/local/T-test/L-example/E-99-unknown.md").as_uri(),
        )
        self.assertEqual(result["matches"], [])

    def test_binding_formats_must_belong_to_the_domain(self) -> None:
        text = self.protocol.read_text(encoding="utf-8")
        self.protocol.write_text(
            text.replace(
                'formats = ["md", "ipynb"]\ninventory',
                'formats = ["mp4"]\ninventory',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ResolverError, "exceeds its domain formats"):
            load_contributor(self.protocol)

    def test_unknown_projection_axis_is_rejected(self) -> None:
        with self.assertRaisesRegex(ResolverError, "unknown contributor store"):
            discover_contributor(load_contributor(self.protocol), store="youtube")

    def test_id_and_path_selector_must_agree(self) -> None:
        with self.assertRaisesRegex(ResolverError, "do not identify the same target"):
            discover_contributor(
                load_contributor(self.protocol),
                node_id=NODE_ID,
                rooted_path="T-test/L-example/E-99-other",
            )

    def test_generated_protocol_is_a_valid_scaffold(self) -> None:
        scaffold = self.root / "generated.toml"
        scaffold.write_text(
            contributor_template("example", "documents", ["md"]),
            encoding="utf-8",
        )
        package = load_contributor(scaffold)
        self.assertEqual(package["contributor"], "example")
        self.assertEqual(package["bindings"][0]["formats"], ["md"])


class DirectoryMapStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        archive = self.root / "storage/archive"
        archive.mkdir(parents=True)
        (archive / "final-cut_v2.mp4").write_bytes(b"video")
        (archive / "routes.toml").write_text(
            f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "mp4"
location = "final-cut_v2.mp4"
''',
            encoding="utf-8",
        )
        (self.root / "contributor.toml").write_text(
            '''version = 1

[contributor]
id = "studio"

[domains.videos]
formats = ["mp4"]

[stores.local-videos]
kind = "directory"
enabled = true
strategy = "map"
origin = "storage/archive"

[[bindings]]
domain = "videos"
store = "local-videos"
formats = ["mp4"]
inventory = "storage/archive/routes.toml"
''',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_directory_map_resolves_an_irregular_local_name(self) -> None:
        package = load_contributor(self.root)
        result = project_contributor(package, node_id=NODE_ID)
        expected = (self.root / "storage/archive/final-cut_v2.mp4").resolve().as_uri()
        self.assertEqual(result["locations"][0]["uri"], expected)

    def test_directory_map_is_portable_and_identifiable(self) -> None:
        package = load_contributor(self.root)
        uri = (self.root / "storage/archive/final-cut_v2.mp4").resolve().as_uri()
        result = identify_contributor(package, uri)
        self.assertEqual(result["matches"][0]["target"]["selector"]["id"], NODE_ID)


if __name__ == "__main__":
    unittest.main()
