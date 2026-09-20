from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag.knowledge_service.knowledge_document_backends import LocalTextDocumentBackend
from rag.knowledge_service.knowledge_interfaces import ParseRequest


class KnowledgeDocumentBackendsTest(unittest.TestCase):
    def test_local_markdown_parser_preserves_section_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.md"
            path.write_text(
                "# Demo\n\nIntro text.\n\n## Features\n\nFast voice agents.\n\n### Pricing\n\nUsage based.",
                encoding="utf-8",
            )

            document = LocalTextDocumentBackend().parse(
                ParseRequest(
                    file_path=str(path),
                    company_id="globifye",
                    document_id="doc-1",
                    title="Demo",
                    source_type="md",
                )
            )

        self.assertEqual(document.company_id, "globifye")
        self.assertEqual(document.metadata["parser_provider"], "local_text")
        self.assertEqual([section.heading for section in document.sections], ["Demo", "Features", "Pricing"])
        self.assertEqual(document.sections[-1].section_path, ("Demo", "Features", "Pricing"))


if __name__ == "__main__":
    unittest.main()
