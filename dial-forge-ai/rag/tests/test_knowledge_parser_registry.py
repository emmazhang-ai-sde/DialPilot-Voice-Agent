from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_interfaces import ParseRequest
from rag.knowledge_service.knowledge_parser_registry import ParserRegistry


class KnowledgeParserRegistryTest(unittest.TestCase):
    def test_text_formats_use_local_parser_before_managed_providers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "faq.md"
            path.write_text("# FAQ\n\nAnswers live here.", encoding="utf-8")

            document = ParserRegistry.from_config(KnowledgeProviderConfig.from_env({})).parse(
                ParseRequest(
                    file_path=str(path),
                    company_id="globifye",
                    document_id="faq",
                    title="FAQ",
                    source_type="md",
                )
            )

        self.assertEqual(document.metadata["parser_provider"], "local_text")
        self.assertEqual(document.sections[0].text, "Answers live here.")


if __name__ == "__main__":
    unittest.main()
