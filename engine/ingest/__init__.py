"""Workstream A. File -> chunks with text, page, bbox, keywords, tags, embedding.

Modules (one per task in docs/PLAN.md):
  extract.py    A1  extract_pages(path) -> list[Page]
  chunker.py    A2  chunk_pages(doc_id, pages) -> list[Chunk]
  embed.py      A3  embed_texts(texts) -> np.ndarray
  tagger.py     A4  tag_document(filename, text) -> dict
  keywords.py   A5  extract_keywords(text, lang), detect_lang(text)
  pipeline.py   A6  ingest_file(path, store) -> IngestResult
  textract.py   A7  (stretch) ocr_page(path, page) -> list[Block]
"""
