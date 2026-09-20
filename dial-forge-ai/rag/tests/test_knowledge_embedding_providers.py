from __future__ import annotations

import unittest

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_embedding import DeterministicEmbeddingProvider
from rag.knowledge_service.knowledge_embedding_providers import (
    CohereEmbeddingProvider,
    build_embedding_provider,
)


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return FakeResponse({"embeddings": {"float": [[0.1, 0.2], [0.3, 0.4]]}})


class KnowledgeEmbeddingProvidersTest(unittest.TestCase):
    def test_build_embedding_provider_falls_back_to_deterministic(self) -> None:
        provider = build_embedding_provider(KnowledgeProviderConfig.from_env({}))

        self.assertIsInstance(provider, DeterministicEmbeddingProvider)

    def test_cohere_provider_normalizes_embeddings(self) -> None:
        session = FakeSession()
        provider = CohereEmbeddingProvider(
            api_key="secret",
            model_name="embed-v4.0",
            session=session,
        )

        embeddings = provider.embed_texts(["one", "two"])

        self.assertEqual(embeddings, [[0.1, 0.2], [0.3, 0.4]])
        self.assertEqual(session.calls[0][1]["json"]["texts"], ["one", "two"])
        self.assertEqual(session.calls[0][1]["json"]["model"], "embed-v4.0")


if __name__ == "__main__":
    unittest.main()
