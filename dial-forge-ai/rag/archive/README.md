# Legacy RAG Archive

This folder keeps the pre-KnowledgeService RAG scripts for reference:

- `legacy_ingest.py`: OpenAI embedding + Supabase `sip_kb_chunks` ingest job.
- `legacy_retrieve.py`: standalone Supabase retrieval smoke script.
- `legacy_retrieval.py`: old call-time retrieval helper.

Active runtime imports should use `rag.retrieval`, which now routes through the
`KnowledgeService` boundary.
