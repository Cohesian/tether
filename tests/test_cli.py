from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tether.cli import main


NODE_ID = "11111111-1111-4111-8111-111111111111"
NODE_PATH = "T-test/L-example/E-01-paper"


class GroupedCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "research"
        source = self.root / "storage/local/T-test/L-example"
        source.mkdir(parents=True)
        (source / "E-01-paper.md").write_text("# Paper\n", encoding="utf-8")
        (self.root / "storage/local/routes.toml").write_text(
            f'''version = 1

[[route]]
id = "{NODE_ID}"
path = "{NODE_PATH}"
format = "md"
''',
            encoding="utf-8",
        )
        (self.root / "contributor.toml").write_text(
            '''version = 1

[contributor]
id = "research"

[domains.documents]
formats = ["md"]

[stores.local]
kind = "directory"
enabled = true
strategy = "template"
origin = "storage/local"

[[bindings]]
domain = "documents"
store = "local"
formats = ["md"]
inventory = "storage/local/routes.toml"
pattern = "{path}.{format}"
''',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(argv)
        return status, output.getvalue()

    def test_contributor_check_reports_compatibility(self) -> None:
        status, output = self._run(
            "contributor", "check", str(self.root), "--output", "json"
        )
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(payload["compatibility"], "compatible")

    def test_contributor_check_has_a_human_table(self) -> None:
        status, output = self._run("contributor", "check", str(self.root))
        self.assertEqual(status, 0)
        self.assertIn("compatibility", output)
        self.assertIn("compatible", output)

    def test_resource_resolve_returns_grouped_locations(self) -> None:
        status, output = self._run(
            "resource",
            "resolve",
            str(self.root),
            "--format",
            "md",
            "--output",
            "json",
        )
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(len(payload["resources"]), 1)
        self.assertEqual(payload["resources"][0]["locations"][0]["store"], "local")

    def test_pull_dir_materializes_the_selected_store(self) -> None:
        destination = Path(self.temp.name) / "snapshot"
        status, output = self._run(
            "pull",
            str(self.root),
            "--store",
            "local",
            "--domain",
            "documents",
            "--format",
            "md",
            "--into",
            str(destination),
            "--layout",
            "dir",
            "--output",
            "json",
        )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["resources"], 1)
        self.assertTrue((destination / f"{NODE_PATH}.md").is_file())

    def test_resource_digest_reports_protocol_sha(self) -> None:
        paper = self.root / "storage/local/T-test/L-example/E-01-paper.md"
        status, output = self._run(
            "resource",
            "digest",
            str(paper),
            "--protocol",
            "markdown-file@1",
            "--output",
            "json",
        )
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(len(payload["sha256"]), 64)

        status, verify_output = self._run(
            "resource",
            "verify",
            str(paper),
            "--protocol",
            "markdown-file@1",
            "--sha256",
            payload["sha256"],
            "--output",
            "json",
        )
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(verify_output)["valid"])

    def test_contributor_init_defaults_to_v2(self) -> None:
        generated = Path(self.temp.name) / "generated"
        status, output = self._run(
            "contributor",
            "init",
            str(generated),
            "--id",
            "example",
            "--hierarchy",
            "media/videos",
            "--output",
            "json",
        )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["version"], 2)
        protocol = (generated / "contributor.toml").read_text(encoding="utf-8")
        self.assertIn("version = 2", protocol)
        self.assertTrue(
            (generated / "storage/media/videos/resources.toml").is_file()
        )
        status, check_output = self._run(
            "contributor", "check", str(generated), "--output", "json"
        )
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(check_output)["valid"])


if __name__ == "__main__":
    unittest.main()
