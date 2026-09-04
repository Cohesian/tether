from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORIES_ROOT = Path(__file__).resolve().parents[2]
K_ROOT = REPOSITORIES_ROOT / "k-graph"
K_TOOLING = K_ROOT / "tooling"
sys.path.insert(0, str(K_TOOLING))

from tether import compare_k_registry, load_contributor  # noqa: E402

try:
    from to_neo4j import load_directory_graph  # noqa: E402
except SystemExit:
    load_directory_graph = None


def accepted_records(graph: object, contributor: str) -> list[dict[str, object]]:
    return [
        {
            "node_id": node.id,
            "contributor": resource.contributor,
            "hierarchy": list(resource.hierarchy),
            "key": resource.key,
            "protocol": resource.protocol,
            "sha256": resource.sha256,
        }
        for node in graph.nodes.values()
        for resource in node.contributions
        if resource.contributor == contributor
    ]


@unittest.skipIf(load_directory_graph is None, "K integration requires PyYAML")
class KRegistryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert load_directory_graph is not None
        cls.graph = load_directory_graph(K_ROOT)
        if cls.graph.errors:
            raise AssertionError("invalid K graph: " + "; ".join(cls.graph.errors))

    def test_research_matches_every_accepted_k_record(self) -> None:
        package = load_contributor(REPOSITORIES_ROOT / "research")
        result = compare_k_registry(
            package,
            accepted_records(self.graph, "research"),
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["unregistered"], [])
        self.assertEqual(result["mismatched"], [])

    def test_research_is_the_only_registered_contributor(self) -> None:
        self.assertEqual(self.graph.registered_contributors, {"research"})
        accepted = {
            resource.contributor
            for node in self.graph.nodes.values()
            for resource in node.contributions
        }
        self.assertEqual(accepted, {"research"})


if __name__ == "__main__":
    unittest.main()
