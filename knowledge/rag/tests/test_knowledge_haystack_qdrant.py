from __future__ import annotations

import unittest

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_haystack_qdrant import decide_qdrant_integration


class KnowledgeHaystackQdrantTest(unittest.TestCase):
    def test_uses_wrapped_qdrant_until_tenant_filters_are_validated(self) -> None:
        decision = decide_qdrant_integration(KnowledgeProviderConfig.from_env({}))

        self.assertTrue(decision.official_integration_available)
        self.assertEqual(decision.selected_strategy, "wrapped_globifye_qdrant")
        self.assertIn("tenant filter", decision.reason)

    def test_selects_official_qdrant_after_required_checks(self) -> None:
        decision = decide_qdrant_integration(
            KnowledgeProviderConfig.from_env({"QDRANT_COLLECTION": "test_chunks"}),
            tenant_filter_validated=True,
            metadata_roundtrip_validated=True,
        )

        self.assertTrue(decision.use_official_haystack)
        self.assertEqual(decision.collection, "test_chunks")


if __name__ == "__main__":
    unittest.main()
