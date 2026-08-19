from __future__ import annotations

import unittest

from tether import ResolverError, identify, resolve, resolve_discoveries


NODE_ID = "11111111-1111-4111-8111-111111111111"
NODE_PATH = "T-test/L-example/F-01-paper"
TARGET = {
    "selector": {"id": NODE_ID, "path": NODE_PATH},
    "contribution": {
        "contributor": "research",
        "domain": "documents",
        "format": "md",
    },
}
TEMPLATE_DESCRIPTOR = {
    "version": 1,
    "store": "local",
    "contributor": "research",
    "domain": "documents",
    "strategy": "template",
    "origin": "file:///tmp/research",
    "pattern": "{path}.{format}",
}
DRIVE_URI = "https://drive.google.com/file/d/example/view"
MAP_DESCRIPTOR = {
    "version": 1,
    "store": "google-drive",
    "contributor": "research",
    "domain": "documents",
    "strategy": "map",
    "locations": [{"target": TARGET, "uri": DRIVE_URI}],
}


class ResolverTests(unittest.TestCase):
    def test_resolves_template_forward(self) -> None:
        result = resolve(TARGET, TEMPLATE_DESCRIPTOR)
        self.assertEqual(
            result["uri"],
            "file:///tmp/research/T-test/L-example/F-01-paper.md",
        )

    def test_identifies_template_uri(self) -> None:
        targets = identify(
            "file:///tmp/research/T-test/L-example/F-01-paper.md",
            TEMPLATE_DESCRIPTOR,
        )
        self.assertEqual(targets[0]["selector"], {"path": NODE_PATH})
        self.assertEqual(targets[0]["contribution"], TARGET["contribution"])

    def test_resolves_explicit_map_forward_and_reverse(self) -> None:
        self.assertEqual(resolve(TARGET, MAP_DESCRIPTOR)["uri"], DRIVE_URI)
        self.assertEqual(identify(DRIVE_URI, MAP_DESCRIPTOR), [TARGET])

    def test_rejects_contributor_mismatch(self) -> None:
        target = {
            **TARGET,
            "contribution": {**TARGET["contribution"], "contributor": "studio"},
        }
        with self.assertRaisesRegex(ResolverError, "contributor does not match"):
            resolve(target, TEMPLATE_DESCRIPTOR)

    def test_resolves_a_discovery_batch(self) -> None:
        payload = {
            "version": 1,
            "contributor": "research",
            "discoveries": [
                {
                    "target": TARGET,
                    "stores": [
                        {"name": "local", "descriptor": TEMPLATE_DESCRIPTOR},
                        {"name": "google-drive", "descriptor": MAP_DESCRIPTOR},
                    ],
                }
            ],
        }
        result = resolve_discoveries(payload)
        self.assertEqual(len(result["locations"]), 2)
        self.assertEqual(
            {item["uri"] for item in result["locations"]},
            {
                "file:///tmp/research/T-test/L-example/F-01-paper.md",
                DRIVE_URI,
            },
        )


if __name__ == "__main__":
    unittest.main()
