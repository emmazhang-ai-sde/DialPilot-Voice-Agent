from __future__ import annotations

import unittest

from rag.knowledge_service.knowledge_haystack_adapter import HaystackChunkAdapter, HaystackChunkingConfig
from rag.knowledge_service.knowledge_models import NormalizedDocument, Section


class KnowledgeHaystackAdapterTest(unittest.TestCase):
    def test_chunking_preserves_tenant_and_citation_metadata(self) -> None:
        document = NormalizedDocument(
            document_id="doc-1",
            company_id="globifye",
            title="Demo",
            source_type="md",
            source_uri="kb/demo.md",
            metadata={"knowledge_base_id": "kb-1", "allowed_agent_ids": ["agent-1"]},
            sections=(
                Section(
                    section_id="section-1",
                    heading="Features",
                    text="alpha beta gamma delta epsilon zeta",
                    path=("Demo", "Features"),
                    page_start=2,
                ),
            ),
        )

        chunks = HaystackChunkAdapter(HaystackChunkingConfig(split_length=3, split_overlap=0)).chunk(document)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual({chunk.company_id for chunk in chunks}, {"globifye"})
        self.assertEqual(chunks[0].source.page, 2)
        self.assertEqual(chunks[0].source.section, "Demo > Features")
        self.assertEqual(chunks[0].metadata["knowledge_base_id"], "kb-1")
        self.assertEqual(chunks[0].metadata["allowed_agent_ids"], ["agent-1"])


if __name__ == "__main__":
    unittest.main()
