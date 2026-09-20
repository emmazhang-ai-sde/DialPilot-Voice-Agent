from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag.knowledge_service import KnowledgeRetrievalOptions, KnowledgeService, ParseRequest


class KnowledgeServiceTest(unittest.TestCase):
    def test_ingest_and_retrieve_are_company_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.md"
            path.write_text(
                "# Demo\n\n## Pricing\n\nGlobiFYE pricing supports usage based phone automation.",
                encoding="utf-8",
            )

            service = KnowledgeService.from_env()
            ingest_result = service.ingest(
                ParseRequest(
                    file_path=str(path),
                    company_id="globifye",
                    document_id="doc-pricing",
                    title="Demo",
                    source_type="md",
                    metadata={"knowledge_base_id": "kb-globifye"},
                )
            )

            same_company = service.retrieve(
                company_id="globifye",
                query="pricing phone automation",
                options=KnowledgeRetrievalOptions(top_k=3),
            )
            other_company = service.retrieve(company_id="pacificbeef", query="pricing phone automation")

        self.assertEqual(ingest_result.vector_upsert_count, ingest_result.chunk_count)
        self.assertTrue(same_company.has_evidence)
        self.assertFalse(other_company.has_evidence)
        self.assertEqual(same_company.rows[0]["company_id"], "globifye")
        self.assertEqual(same_company.rows[0]["metadata"]["knowledge_base_id"], "kb-globifye")

    def test_retrieval_handler_matches_existing_runtime_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.md"
            path.write_text("# Demo\n\n## Security\n\nTenant scoped retrieval keeps customer data separate.", encoding="utf-8")
            service = KnowledgeService.from_env()
            service.ingest(
                ParseRequest(
                    file_path=str(path),
                    company_id="globifye",
                    document_id="doc-security",
                    title="Demo",
                    source_type="md",
                )
            )

            rows = service.retrieval_handler(company_key="globifye", query="tenant retrieval", k=1)

        self.assertEqual(len(rows), 1)
        self.assertIn("content", rows[0])
        self.assertIn("source_file", rows[0])
        self.assertIn("section", rows[0])


if __name__ == "__main__":
    unittest.main()
