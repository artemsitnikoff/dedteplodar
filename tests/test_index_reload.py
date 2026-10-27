"""Hot reload of embeddings_*.npy / metadata_*.pkl in SimpleRetriever / HybridRetriever."""
import pickle

import numpy as np
import pytest

from src.rag.hybrid_retriever import HybridRetriever
from src.rag.simple_retriever import SimpleRetriever

DIM = 64


class FakeEmbedder:
    """Deterministic hashed-character-bigram embedding — no model needed."""

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(DIM, dtype=np.float32)
        t = f" {text.lower()} "
        for a, b in zip(t, t[1:]):
            v[(ord(a) * 31 + ord(b)) % DIM] += 1.0
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_queries(self, texts, batch_size=32):
        return np.stack([self._vec(t) for t in texts])

    def embed_passages(self, texts, batch_size=32):
        return np.stack([self._vec(t) for t in texts])

    def get_embedding_dimension(self):
        return DIM


def meta(chunk_id, text, chunk_type="product"):
    return {"chunk_id": chunk_id, "chunk_text": text, "chunk_type": chunk_type,
            "product_id": chunk_id, "document_id": None, "category_id": None, "position": 0}


def write_index(data_dir, rows):
    """Simulate the sync process writing a new index from another process."""
    emb = FakeEmbedder()
    w = SimpleRetriever(emb, "v", str(data_dir))
    w.save_index(emb.embed_passages([r["chunk_text"] for r in rows]), rows)


@pytest.fixture
def index_dir(tmp_path):
    write_index(tmp_path, [meta(1, "котёл куппер про 22"), meta(2, "печь русь 12")])
    return tmp_path


def test_reload_picks_up_new_files_and_rebuilds_bm25(index_dir):
    r = HybridRetriever(FakeEmbedder(), "v", str(index_dir), reload_interval=0.0)
    assert [x.id for x in r.search(None, "куппер", k=1)] == [1]
    assert [x.id for x in r.search(None, "альфа", k=5)] and 3 not in [x.id for x in r.search(None, "альфа", k=5)]

    write_index(index_dir, [meta(1, "котёл куппер про 22"), meta(3, "котёл альфа 20")])
    assert r.reload_index() is True
    ids = [x.id for x in r.search(None, "альфа", k=1)]
    assert ids == [3]
    assert len(r.chunk_metadata) == 2 and 2 not in [m["chunk_id"] for m in r.chunk_metadata]


def test_search_path_reloads_without_explicit_call(index_dir):
    r = HybridRetriever(FakeEmbedder(), "v", str(index_dir), reload_interval=0.0)
    r.search(None, "печь", k=1)
    write_index(index_dir, [meta(5, "дымоход сэндвич")])
    assert [x.id for x in r.search(None, "дымоход", k=1)] == [5]


def test_rate_limited_and_unchanged_files_do_not_reload(index_dir):
    d = SimpleRetriever(FakeEmbedder(), "v", str(index_dir))
    assert d.maybe_reload(force=True) is False            # nothing changed
    write_index(index_dir, [meta(9, "x")])
    assert d.maybe_reload(min_interval=3600) is False     # checked at __init__ just now
    assert d.maybe_reload(force=True) is True
    assert d.chunk_metadata[0]["chunk_id"] == 9


def test_inconsistent_files_keep_the_old_index(index_dir):
    d = SimpleRetriever(FakeEmbedder(), "v", str(index_dir))
    before = d.chunk_metadata
    # metadata rewritten with a different row count (writer caught mid-way)
    with open(d.metadata_path, "wb") as f:
        pickle.dump([meta(1, "a")], f)
    assert d.maybe_reload(force=True) is False
    assert d.chunk_metadata is before and d.embeddings.shape[0] == 2
    # the matching npy lands → next check succeeds
    with open(d.embeddings_path, "wb") as f:
        np.save(f, FakeEmbedder().embed_passages(["a"]))
    assert d.maybe_reload(force=True) is True
    assert len(d.chunk_metadata) == 1


def test_save_index_is_atomic_and_validated(tmp_path):
    d = SimpleRetriever(FakeEmbedder(), "v", str(tmp_path))
    with pytest.raises(ValueError):
        d.save_index(np.zeros((2, DIM), dtype=np.float32), [meta(1, "a")])
    d.save_index(np.zeros((1, DIM), dtype=np.float32), [meta(1, "a")])
    assert not list(tmp_path.glob("*.tmp"))
    assert d.embeddings_path.exists() and d.metadata_path.exists()
