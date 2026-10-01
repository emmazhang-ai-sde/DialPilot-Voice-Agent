from __future__ import annotations

import unittest

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_embedding import DeterministicEmbeddingProvider
from rag.knowledge_service.knowledge_interfaces import VectorSearchQuery
from rag.knowledge_service.knowledge_models import Chunk, SourceMetadata
from rag.knowledge_service.knowledge_retrieval import QdrantKnowledgeRetrievalBackend, RetrievalRequest
from rag.knowledge_service.knowledge_vector_store import (
    chunk_from_qdrant_point,
    InMemoryVectorStore,
    QdrantVectorStore,
    VectorStoreRegistry,
    qdrant_payload,
    stable_qdrant_point_id,
)


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, get_response: FakeResponse | None = None, post_response: FakeResponse | None = None):
        self.calls: list[tuple[str, str, dict]] = []
        self.get_response = get_response or FakeResponse(
            body={
                "result": {
                    "config": {
                        "params": {
                            "vectors": {"size": 3, "distance": "Cosine"}
                        }
                    }
                }
            }
        )
        self.post_response = post_response or FakeResponse(body={"result": []})

    def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.get_response

    def put(self, url: str, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return FakeResponse(body={"result": {"operation_id": 1}})

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.post_response


class KnowledgeVectorStoreTest(unittest.TestCase):
    def test_qdrant_payload_preserves_tenant_and_citation_metadata(self) -> None:
        payload = qdrant_payload(_chunk())

        self.assertEqual(payload["company_id"], "globifye")
        self.assertEqual(payload["document_id"], "doc-1")
        self.assertEqual(payload["chunk_id"], "chunk-1")
        self.assertEqual(payload["document_name"], "Demo")
        self.assertEqual(payload["page"], 3)
        self.assertEqual(payload["section"], "Demo > Pricing")
        self.assertEqual(payload["content"], "Pricing content")
        self.assertEqual(payload["text"], "Pricing content")
        self.assertEqual(payload["tenant"]["company_id"], "globifye")
        self.assertEqual(payload["tenant"]["knowledge_base_id"], "kb-1")
        self.assertEqual(payload["tenant"]["allowed_agent_ids"], ["agent-1"])
        self.assertEqual(payload["tenant"]["document_status"], "active")
        self.assertEqual(payload["source"]["section"], "Demo > Pricing")

    def test_upsert_uses_stable_point_ids_and_points_endpoint(self) -> None:
        session = FakeSession()
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="globifye_knowledge_chunks",
            session=session,
        )

        count = store.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

        self.assertEqual(count, 1)
        put_calls = [call for call in session.calls if call[0] == "PUT"]
        self.assertEqual(len(put_calls), 1)
        _, url, kwargs = put_calls[0]
        self.assertEqual(url, "https://qdrant.example.com/collections/globifye_knowledge_chunks/points")
        point = kwargs["json"]["points"][0]
        self.assertEqual(point["id"], stable_qdrant_point_id("chunk-1"))
        self.assertEqual(point["payload"]["tenant"]["company_id"], "globifye")

    def test_upsert_creates_missing_collection(self) -> None:
        session = FakeSession(get_response=FakeResponse(status_code=404))
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="chunks",
            session=session,
        )

        store.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

        create_calls = [
            call for call in session.calls
            if call[0] == "PUT" and call[1].endswith("/collections/chunks")
        ]
        self.assertEqual(create_calls[0][2]["json"], {"vectors": {"size": 3, "distance": "Cosine"}})

    def test_upsert_rejects_existing_collection_dimension_mismatch(self) -> None:
        session = FakeSession(
            get_response=FakeResponse(
                body={
                    "result": {
                        "config": {
                            "params": {
                                "vectors": {"size": 4, "distance": "Cosine"}
                            }
                        }
                    }
                }
            )
        )
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="chunks",
            session=session,
        )

        with self.assertRaisesRegex(ValueError, "vector size"):
            store.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

    def test_upsert_rejects_existing_collection_distance_mismatch(self) -> None:
        session = FakeSession(
            get_response=FakeResponse(
                body={
                    "result": {
                        "config": {
                            "params": {
                                "vectors": {"size": 3, "distance": "Dot"}
                            }
                        }
                    }
                }
            )
        )
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="chunks",
            session=session,
        )

        with self.assertRaisesRegex(ValueError, "distance"):
            store.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

    def test_upsert_rejects_embedding_count_mismatch(self) -> None:
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="chunks",
            session=FakeSession(),
        )

        with self.assertRaisesRegex(ValueError, "same length"):
            store.upsert_chunks([_chunk()], [])

    def test_search_sends_company_filter_and_maps_hits(self) -> None:
        session = FakeSession(
            post_response=FakeResponse(
                body={
                    "result": {
                        "points": [
                            {
                                "id": stable_qdrant_point_id("chunk-1"),
                                "score": 0.88,
                                "payload": qdrant_payload(_chunk()),
                            }
                        ]
                    }
                }
            )
        )
        store = QdrantVectorStore(
            url="https://qdrant.example.com",
            api_key="secret",
            collection="chunks",
            session=session,
        )

        chunks = store.search(
            query=VectorSearchQuery(
                company_id="globifye",
                query_embedding=(0.1, 0.2, 0.3),
                top_k=1,
            )
        )

        post_call = [call for call in session.calls if call[0] == "POST"][0]
        self.assertEqual(post_call[1], "https://qdrant.example.com/collections/chunks/points/query")
        self.assertEqual(post_call[2]["json"]["query"], [0.1, 0.2, 0.3])
        self.assertNotIn("vector", post_call[2]["json"])
        must = post_call[2]["json"]["filter"]["must"]
        self.assertIn({"key": "company_id", "match": {"value": "globifye"}}, must)
        self.assertIn({"key": "tenant.company_id", "match": {"value": "globifye"}}, must)
        self.assertEqual(chunks[0].chunk_id, "chunk-1")
        self.assertEqual(chunks[0].score, 0.88)

    def test_chunk_from_qdrant_point_restores_runtime_chunk(self) -> None:
        chunk = chunk_from_qdrant_point(
            {
                "id": stable_qdrant_point_id("chunk-1"),
                "score": 0.77,
                "payload": qdrant_payload(_chunk()),
            }
        )

        self.assertEqual(chunk.chunk_id, "chunk-1")
        self.assertEqual(chunk.company_id, "globifye")
        self.assertEqual(chunk.source.section, "Demo > Pricing")
        self.assertEqual(chunk.score, 0.77)

    def test_qdrant_retrieval_backend_embeds_query_and_searches_store(self) -> None:
        vector_store = InMemoryVectorStore()
        embedding_provider = DeterministicEmbeddingProvider(dimensions=8)
        vector_store.upsert_chunks(
            [_chunk()],
            embedding_provider.embed_texts(["pricing content"]),
        )
        backend = QdrantKnowledgeRetrievalBackend(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )

        rows = backend.retrieve_dicts(
            RetrievalRequest(company_id="globifye", query="pricing content", top_k=1)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company_id"], "globifye")
        self.assertEqual(rows[0]["chunk_id"], "chunk-1")

    def test_registry_uses_qdrant_only_when_credentials_are_ready(self) -> None:
        fallback = VectorStoreRegistry.from_config(KnowledgeProviderConfig.from_env({}))
        configured = VectorStoreRegistry.from_config(
            KnowledgeProviderConfig.from_env(
                {
                    "QDRANT_URL": "https://qdrant.example.com",
                    "QDRANT_API_KEY": "secret",
                    "QDRANT_COLLECTION": "chunks",
                }
            ),
            session=FakeSession(),
        )

        self.assertIsInstance(fallback, InMemoryVectorStore)
        self.assertIsInstance(configured, QdrantVectorStore)

    def test_local_qdrant_store_allows_missing_api_key(self) -> None:
        store = QdrantVectorStore(
            url="http://localhost:6333",
            api_key="",
            collection="chunks",
            session=FakeSession(),
        )

        self.assertEqual(store._headers(), {"content-type": "application/json"})

    def test_remote_qdrant_store_requires_api_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "API key"):
            QdrantVectorStore(
                url="https://qdrant.example.com",
                api_key="",
                collection="chunks",
                session=FakeSession(),
            )


def _chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        company_id="globifye",
        document_id="doc-1",
        text="Pricing content",
        source=SourceMetadata(
            document_id="doc-1",
            document_name="Demo",
            source_type="md",
            source_uri="kb/demo.md",
            page=3,
            section_path=("Demo", "Pricing"),
        ),
        token_count=2,
        embedding_model="embed-v4.0",
        metadata={
            "knowledge_base_id": "kb-1",
            "allowed_agent_ids": ["agent-1"],
            "document_status": "active",
        },
    )


if __name__ == "__main__":
    unittest.main()
