from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tether import (
    ResolverError,
    check_contributor,
    compare_k_registry,
    discover_contributor,
    identify_contributor,
    inspect_contributor,
    load_contributor,
    materialize_contributor,
    parse_k_contributions,
    project_contributor,
    resource_digest,
    validate_contributor,
)


NODE_ID = "11111111-1111-4111-8111-111111111111"
NODE_PATH = "T-test/L-example/E-01-paper"


class ContributorProtocolV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "research"
        document = self.root / f"storage/documents/local/{NODE_PATH}.md"
        document.parent.mkdir(parents=True)
        document.write_text("# Paper\n", encoding="utf-8")
        self.document = document
        self.digest = resource_digest(document, "markdown-file@1")
        inventory = self.root / "storage/documents/resources.toml"
        inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory.write_text(
            f'''version = 2
contributor = "research"
hierarchy = ["documents"]

[[resource]]
node_id = "{NODE_ID}"
path = "{NODE_PATH}"
key = "md"
protocol = "markdown-file@1"
sha256 = "{self.digest}"
produced_by = "research"
locations = [
  {{ store = "local", relation = "exact", location = "storage/documents/local/{NODE_PATH}.md" }},
  {{ store = "github", relation = "exact", uri = "https://raw.githubusercontent.com/Cohesian/research/main/{NODE_PATH}.md" }},
  {{ store = "youtube", relation = "publication", uri = "https://youtu.be/example" }},
]
''',
            encoding="utf-8",
        )
        (self.root / "contributor.toml").write_text(
            '''version = 2

[contributor]
id = "research"

[stores.local]
kind = "directory"
enabled = true
origin = "."

[stores.github]
kind = "remote"
enabled = true

[stores.youtube]
kind = "publication"
enabled = true

[[inventory]]
hierarchy = ["documents"]
path = "storage/documents/resources.toml"
''',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_loads_and_inspects_v2_package(self) -> None:
        package = load_contributor(self.root)
        self.assertEqual(package["version"], 2)
        result = inspect_contributor(package)
        self.assertEqual(result["hierarchies"][0]["path"], ["documents"])
        self.assertEqual(result["resources"], 1)

    def test_check_validates_the_local_exact_digest(self) -> None:
        result = check_contributor(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(result["compatibility"], "compatible")
        self.assertEqual(result["verified_exact_local"], 1)
        self.assertFalse(result["legacy"])

    def test_digest_mismatch_is_rejected(self) -> None:
        self.document.write_text("# Changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ResolverError, "digest mismatch"):
            validate_contributor(load_contributor(self.root))

    def test_discovers_hierarchy_key_protocol_store_and_relation(self) -> None:
        result = discover_contributor(
            load_contributor(self.root),
            hierarchy="documents",
            resource_key="md",
            protocol="markdown-file@1",
            store="youtube",
            relation="publication",
        )
        discovery = result["discoveries"][0]
        self.assertEqual(discovery["target"]["contribution"]["key"], "md")
        self.assertEqual(discovery["stores"][0]["relation"], "publication")

    def test_project_and_identify_preserve_location_relation(self) -> None:
        package = load_contributor(self.root)
        projected = project_contributor(package, store="youtube")
        self.assertEqual(projected["locations"][0]["store"]["relation"], "publication")
        identified = identify_contributor(package, "https://youtu.be/example")
        self.assertEqual(identified["matches"][0]["relation"], "publication")

    def test_id_and_path_must_select_the_same_resource(self) -> None:
        with self.assertRaisesRegex(ResolverError, "do not identify the same target"):
            discover_contributor(
                load_contributor(self.root),
                node_id=NODE_ID,
                rooted_path="T-test/L-example/E-99-other",
            )

    def test_compares_inventory_with_k_acceptance(self) -> None:
        package = load_contributor(self.root)
        result = compare_k_registry(
            package,
            [
                {
                    "node_id": NODE_ID,
                    "contributor": "research",
                    "hierarchy": ["documents"],
                    "key": "md",
                    "protocol": "markdown-file@1",
                    "sha256": self.digest,
                }
            ],
        )
        self.assertTrue(result["valid"])

    def test_parses_typed_k_overlay_and_compares_it(self) -> None:
        accepted = parse_k_contributions(
            NODE_ID,
            {
                "c_research": {
                    "h_documents": {
                        "r_md": {
                            "protocol": "markdown-file@1",
                            "sha256": self.digest,
                        }
                    }
                }
            },
        )
        self.assertEqual(accepted[0]["hierarchy"], ["documents"])
        self.assertTrue(compare_k_registry(load_contributor(self.root), accepted)["valid"])

    def test_k_overlay_supports_arbitrary_hierarchy_depth(self) -> None:
        accepted = parse_k_contributions(
            NODE_ID,
            {
                "c_research": {
                    "h_media": {
                        "h_videos": {
                            "r_primary": {
                                "protocol": "mp4-file@1",
                                "sha256": "0" * 64,
                            }
                        }
                    }
                }
            },
        )
        self.assertEqual(accepted[0]["hierarchy"], ["media", "videos"])
        self.assertEqual(accepted[0]["key"], "primary")

    def test_k_overlay_rejects_untyped_keys(self) -> None:
        with self.assertRaisesRegex(ResolverError, "start with c_"):
            parse_k_contributions(NODE_ID, {"research": {}})

    def test_k_comparison_detects_digest_mismatch(self) -> None:
        result = compare_k_registry(
            load_contributor(self.root),
            [
                {
                    "node_id": NODE_ID,
                    "contributor": "research",
                    "hierarchy": ["documents"],
                    "key": "md",
                    "protocol": "markdown-file@1",
                    "sha256": "0" * 64,
                }
            ],
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["mismatched"][0]["key"], "md")

    def test_materializes_v2_file_under_resource_key(self) -> None:
        destination = Path(self.temp.name) / "snapshot"
        result = materialize_contributor(
            load_contributor(self.root),
            destination,
            layout="dir",
            store="local",
            hierarchy="documents",
            resource_key="md",
        )
        output = destination / NODE_PATH / "md.md"
        self.assertEqual(output.read_text(encoding="utf-8"), "# Paper\n")
        self.assertEqual(result["version"], 2)
        manifest = json.loads((destination / "tether-manifest.json").read_text())
        resource = manifest["resources"][0]
        self.assertEqual(resource["protocol"], "markdown-file@1")
        self.assertEqual(resource["sha256"], self.digest)

    def test_materializes_markdown_bundle_in_canonical_layout(self) -> None:
        companion = self.document.with_suffix("")
        companion.mkdir()
        (companion / "plot.png").write_bytes(b"image")
        bundle_digest = resource_digest(self.document, "markdown-bundle@1")
        inventory = self.root / "storage/documents/resources.toml"
        inventory.write_text(
            inventory.read_text(encoding="utf-8")
            .replace("markdown-file@1", "markdown-bundle@1")
            .replace(self.digest, bundle_digest),
            encoding="utf-8",
        )
        destination = Path(self.temp.name) / "bundle-snapshot"
        materialize_contributor(
            load_contributor(self.root),
            destination,
            layout="dir",
            store="local",
            resource_key="md",
        )
        bundle = destination / NODE_PATH / "md"
        self.assertEqual((bundle / "document.md").read_text(), "# Paper\n")
        self.assertEqual((bundle / "assets/plot.png").read_bytes(), b"image")

    def test_remote_exact_materialization_verifies_before_publish(self) -> None:
        inventory = self.root / "storage/documents/resources.toml"
        inventory.write_text(
            f'''version = 2
contributor = "research"
hierarchy = ["documents"]

[[resource]]
node_id = "{NODE_ID}"
path = "{NODE_PATH}"
key = "md"
protocol = "markdown-file@1"
sha256 = "{'0' * 64}"
locations = [
  {{ store = "github", relation = "exact", uri = "{self.document.as_uri()}" }},
]
''',
            encoding="utf-8",
        )
        destination = Path(self.temp.name) / "rejected-snapshot"
        with self.assertRaisesRegex(ResolverError, "digest mismatch"):
            materialize_contributor(
                load_contributor(self.root),
                destination,
                layout="dir",
                store="github",
            )
        self.assertFalse((destination / NODE_PATH / "md.md").exists())


class ResourceDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_file_digest_uses_exact_bytes(self) -> None:
        path = self.root / "paper.md"
        path.write_bytes(b"# Paper\n")
        first = resource_digest(path, "markdown-file@1")
        path.write_bytes(b"# Paper\r\n")
        self.assertNotEqual(first, resource_digest(path, "markdown-file@1"))

    def test_markdown_bundle_hashes_entrypoint_and_companions(self) -> None:
        entrypoint = self.root / "paper.md"
        assets = self.root / "paper"
        assets.mkdir()
        entrypoint.write_text("![Plot](paper/plot.png)\n", encoding="utf-8")
        (assets / "plot.png").write_bytes(b"image")
        first = resource_digest(entrypoint, "markdown-bundle@1")
        (assets / ".DS_Store").write_bytes(b"noise")
        self.assertEqual(first, resource_digest(entrypoint, "markdown-bundle@1"))
        (assets / "plot.png").write_bytes(b"changed")
        self.assertNotEqual(first, resource_digest(entrypoint, "markdown-bundle@1"))

    def test_project_digest_requires_declared_members(self) -> None:
        project = self.root / "scene"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        with self.assertRaisesRegex(ResolverError, "missing required members"):
            resource_digest(project, "loci-project@1")

    def test_python_project_digest_ignores_runtime_state(self) -> None:
        project = self.root / "project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
        first = resource_digest(project, "python-project@1")
        for relative in (
            ".pixi/env/python",
            ".cache/state",
            ".pytest_cache/state",
            ".mypy_cache/state",
            ".ruff_cache/state",
            ".tox/state",
            ".nox/state",
            ".ipynb_checkpoints/state",
            "outputs/run.json",
        ):
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("machine-local\n", encoding="utf-8")
        self.assertEqual(first, resource_digest(project, "python-project@1"))

    def test_tree_rejects_env_files(self) -> None:
        project = self.root / "project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (project / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        with self.assertRaisesRegex(ResolverError, "cannot include .env"):
            resource_digest(project, "python-project@1")


if __name__ == "__main__":
    unittest.main()
