"""Document RAG for grounding the council in *project documents* — NOT coilmem.

Uses LangChain's InMemoryVectorStore. The embeddings object is injectable so tests run
offline (pass a deterministic fake); the live default is local all-MiniLM-L6-v2 (keyless,
via langchain-huggingface). Grounding the seats in source docs (vs the council's own prior
answers) gives consistency without anchoring away the council's diversity.
"""
from typing import Optional


class DocRAG:
    def __init__(self, embeddings=None):
        self._embeddings = embeddings
        self._store = None

    def _emb(self):
        if self._embeddings is None:  # lazy: pulls torch only on live use
            from langchain_huggingface import HuggingFaceEmbeddings

            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
        return self._embeddings

    def index(self, docs):
        from langchain_core.vectorstores import InMemoryVectorStore

        self._store = InMemoryVectorStore.from_texts(list(docs), self._emb())
        return self

    def retrieve(self, query: str, k: int = 4):
        if self._store is None:
            return []
        return [d.page_content for d in self._store.similarity_search(query, k=k)]


def load_docs(docs_dir: Optional[str] = None):
    """Read all *.md / *.txt under docs_dir (default: ../docs) as a doc corpus."""
    from pathlib import Path

    base = Path(docs_dir) if docs_dir else Path(__file__).resolve().parent.parent / "docs"
    if not base.is_dir():
        return []
    docs = []
    for p in sorted(base.glob("*.md")) + sorted(base.glob("*.txt")):
        docs.append(p.read_text(encoding="utf-8"))
    return docs
