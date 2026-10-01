from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig, read_env_file


class KnowledgeProviderConfigTest(unittest.TestCase):
    def test_defaults_are_cloud_managed_free_first(self) -> None:
        config = KnowledgeProviderConfig.from_env({})

        self.assertEqual(
            config.provider_order("document"),
            ("azure_document_intelligence", "docling"),
        )
        self.assertEqual(
            config.provider_order("embedding"),
            ("cohere", "gemini", "sentence_transformers"),
        )
        self.assertEqual(
            config.provider_order("vector"),
            ("qdrant", "weaviate", "supabase_pgvector"),
        )
        self.assertEqual(config.provider_order("ocr"), ("azure_document_intelligence", "tesseract"))
        self.assertEqual(config.cohere_embedding_model, "embed-v4.0")
        self.assertEqual(config.gemini_embedding_model, "gemini-embedding-001")
        self.assertEqual(config.qdrant_collection, "globifye_knowledge_chunks")

    def test_missing_credentials_are_secret_safe(self) -> None:
        config = KnowledgeProviderConfig.from_env(
            {
                "COHERE_API_KEY": "secret-cohere",
                "QDRANT_URL": "https://example.qdrant.io",
            }
        )

        self.assertEqual(config.missing_credentials("cohere"), ())
        self.assertEqual(config.missing_credentials("qdrant"), ("QDRANT_API_KEY",))
        readiness = config.readiness()
        self.assertTrue(readiness["cohere"]["configured"])
        self.assertFalse(readiness["qdrant"]["configured"])
        self.assertNotIn("secret-cohere", str(readiness))

    def test_local_qdrant_does_not_require_api_key(self) -> None:
        config = KnowledgeProviderConfig.from_env(
            {"QDRANT_URL": "http://localhost:6333"}
        )

        self.assertEqual(config.missing_credentials("qdrant"), ())
        self.assertTrue(config.is_provider_configured("qdrant"))

    def test_env_file_loading_and_runtime_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "ai-pipeline" / ".env.local"
            env_file.parent.mkdir()
            env_file.write_text(
                "\n".join(
                    [
                        "KNOWLEDGE_EMBEDDING_PROVIDER=gemini",
                        "GEMINI_API_KEY='file-gemini-key'",
                        "QDRANT_URL=https://file-qdrant.example.com",
                        "QDRANT_API_KEY=file-qdrant-key",
                    ]
                ),
                encoding="utf-8",
            )

            config = KnowledgeProviderConfig.from_project_env(
                root,
                env={
                    "KNOWLEDGE_EMBEDDING_PROVIDER": "cohere",
                    "COHERE_API_KEY": "runtime-cohere-key",
                },
            )

        self.assertEqual(config.embedding_provider, "cohere")
        self.assertEqual(config.gemini_api_key, "file-gemini-key")
        self.assertEqual(config.cohere_api_key, "runtime-cohere-key")
        self.assertEqual(config.missing_credentials("qdrant"), ())

    def test_read_env_file_ignores_comments_and_unquoted_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env.local"
            env_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "COHERE_API_KEY=abc123",
                        'GEMINI_API_KEY="quoted-value"',
                        "not valid = skipped",
                    ]
                ),
                encoding="utf-8",
            )

            values = read_env_file(env_file)

        self.assertEqual(values["COHERE_API_KEY"], "abc123")
        self.assertEqual(values["GEMINI_API_KEY"], "quoted-value")
        self.assertNotIn("not valid", values)


if __name__ == "__main__":
    unittest.main()
