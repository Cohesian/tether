from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tether import ResolverError, load_contributor, materialize_contributor
from tether.protocol import check_contributor


NODE_ID = "11111111-1111-4111-8111-111111111111"
NODE_PATH = "T-test/L-example/F-01-paper"


class MaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "contributor"
        local = self.root / "storage/local/T-test/L-example"
        remote = self.root / "storage/youtube"
        local.mkdir(parents=True)
        remote.mkdir(parents=True)
        (local / "F-01-paper.md").write_text("# Paper\n", encoding="utf-8")
        routes = f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "md"
location = "{NODE_PATH}.md"
'''
        (self.root / "storage/local/routes.toml").write_text(
            routes, encoding="utf-8"
        )
        (self.root / "storage/youtube/routes.toml").write_text(
            f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "md"
uri = "https://www.youtube.com/watch?v=example"
''',
            encoding="utf-8",
        )
        (self.root / "contributor.toml").write_text(
            '''version = 1

[contributor]
id = "example"

[domains.documents]
formats = ["md"]

[stores.local]
kind = "directory"
enabled = true
strategy = "template"
origin = "storage/local"

[stores.youtube]
kind = "remote"
enabled = true
strategy = "map"

[[bindings]]
domain = "documents"
store = "local"
formats = ["md"]
inventory = "storage/local/routes.toml"
pattern = "{path}.{format}"

[[bindings]]
domain = "documents"
store = "youtube"
formats = ["md"]
inventory = "storage/youtube/routes.toml"
''',
            encoding="utf-8",
        )
        self.package = load_contributor(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_dir_layout_copies_content_by_rooted_path(self) -> None:
        destination = Path(self.temp.name) / "site-content"
        result = materialize_contributor(
            self.package,
            destination,
            layout="dir",
            store="local",
            domain="documents",
            content_format="md",
        )
        paper = destination / f"{NODE_PATH}.md"
        self.assertEqual(paper.read_text(encoding="utf-8"), "# Paper\n")
        manifest = json.loads((destination / "tether-manifest.json").read_text())
        self.assertEqual(result["resources"], 1)
        self.assertEqual(manifest["layout"], "dir")
        self.assertEqual(
            manifest["resources"][0]["materialized"]["location"],
            f"{NODE_PATH}.md",
        )

    def test_map_layout_preserves_uri_without_downloading(self) -> None:
        destination = Path(self.temp.name) / "site-map"
        materialize_contributor(
            self.package,
            destination,
            layout="map",
            store="youtube",
            domain="documents",
            content_format="md",
        )
        manifest = json.loads((destination / "tether-manifest.json").read_text())
        location = manifest["resources"][0]["locations"][0]
        self.assertEqual(location["store"], "youtube")
        self.assertEqual(
            location["uri"], "https://www.youtube.com/watch?v=example"
        )
        self.assertEqual(list(destination.iterdir()), [destination / "tether-manifest.json"])

    def test_dir_layout_copies_a_local_project_directory(self) -> None:
        project = self.root / "storage/local/T-test/L-example/F-02-scene"
        (project / "scenes").mkdir(parents=True)
        (project / "pyproject.toml").write_text(
            '[project]\nname = "scene"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        (project / "scenes/scene.py").write_text(
            "class Scene: pass\n", encoding="utf-8"
        )
        (self.root / "storage/local/projects.toml").write_text(
            f'''version = 1

[[route]]
id = "22222222-2222-4222-8222-222222222222"
path = "T-test/L-example/F-02-scene"
format = "loci-project"
location = "T-test/L-example/F-02-scene"
''',
            encoding="utf-8",
        )
        protocol = self.root / "contributor.toml"
        protocol.write_text(
            protocol.read_text(encoding="utf-8")
            + '''

[domains.scenes]
formats = ["loci-project"]

[[bindings]]
domain = "scenes"
store = "local"
formats = ["loci-project"]
inventory = "storage/local/projects.toml"
pattern = "{path}"
''',
            encoding="utf-8",
        )
        package = load_contributor(self.root)
        destination = Path(self.temp.name) / "scene-content"
        result = materialize_contributor(
            package,
            destination,
            layout="dir",
            store="local",
            domain="scenes",
            content_format="loci-project",
        )
        exported = destination / "T-test/L-example/F-02-scene"
        self.assertTrue((exported / "pyproject.toml").is_file())
        self.assertTrue((exported / "scenes/scene.py").is_file())
        manifest = json.loads((destination / "tether-manifest.json").read_text())
        self.assertEqual(result["resources"], 1)
        self.assertEqual(
            manifest["resources"][0]["materialized"]["location"],
            "T-test/L-example/F-02-scene",
        )
        (exported / "stale.txt").write_text("old\n", encoding="utf-8")
        materialize_contributor(
            package,
            destination,
            layout="dir",
            force=True,
            store="local",
            domain="scenes",
            content_format="loci-project",
        )
        self.assertFalse((exported / "stale.txt").exists())
        self.assertTrue((exported / "scenes/scene.py").is_file())

    def test_dir_layout_rejects_non_downloadable_scheme(self) -> None:
        with self.assertRaisesRegex(ResolverError, "use --layout map"):
            materialize_contributor(
                self.package,
                Path(self.temp.name) / "video",
                layout="dir",
                store="youtube",
            )

    def test_pull_requires_an_explicit_store(self) -> None:
        with self.assertRaisesRegex(ResolverError, "requires one explicit store"):
            materialize_contributor(
                self.package,
                Path(self.temp.name) / "output",
                layout="map",
            )

    def test_check_reports_newer_protocol_without_loading_it(self) -> None:
        protocol = self.root / "contributor.toml"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace("version = 1", "version = 3", 1),
            encoding="utf-8",
        )
        result = check_contributor(self.root)
        self.assertEqual(result["compatibility"], "newer")
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
