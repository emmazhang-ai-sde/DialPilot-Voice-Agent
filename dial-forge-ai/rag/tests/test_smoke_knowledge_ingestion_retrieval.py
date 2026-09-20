from __future__ import annotations

import unittest

from rag.smoke_knowledge_ingestion_retrieval import enforce_qdrant_smoke_guard, is_local_qdrant_url


class SmokeKnowledgeIngestionRetrievalTest(unittest.TestCase):
    def test_allows_local_qdrant_without_cloud_flag(self) -> None:
        enforce_qdrant_smoke_guard(
            qdrant_url="http://localhost:6333",
            env={},
        )

    def test_rejects_cloud_qdrant_without_explicit_flag(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Refusing"):
            enforce_qdrant_smoke_guard(
                qdrant_url="https://cluster.qdrant.io",
                env={},
            )

    def test_allows_cloud_qdrant_with_env_flag(self) -> None:
        enforce_qdrant_smoke_guard(
            qdrant_url="https://cluster.qdrant.io",
            env={"RUN_QDRANT_CLOUD_SMOKE": "1"},
        )

    def test_local_url_detection(self) -> None:
        self.assertTrue(is_local_qdrant_url("http://127.0.0.1:6333"))
        self.assertFalse(is_local_qdrant_url("https://cluster.qdrant.io"))


if __name__ == "__main__":
    unittest.main()
