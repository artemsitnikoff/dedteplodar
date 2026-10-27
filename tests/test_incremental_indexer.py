"""IncrementalIndexer: splice changed products into the live npy/pkl index."""
import numpy as np
import pytest
from sqlalchemy import select

from src.core.database import SessionLocal, create_tables
from src.documents.models import Document, DocumentType
from src.products.models import Category, Product, ProductParam
from src.rag.chunker import ChunkData
from src.rag.incremental_indexer import IncrementalIndexer
from src.rag.models import Chunk
from src.rag.simple_retriever import SimpleRetriever
from tests.test_index_reload import FakeEmbedder

V = "test-v"


class FakeChunker:
    def chunk_product(self, product, params, category):
        text = f"Товар: {product.name}"
        return [ChunkData(text, text, "product", product.id, None, product.category_id, 0, 5)]

    def chunk_document(self, doc, product=None):
        # no product prefix: boilerplate shared by two manuals must embed identically
        return [ChunkData(doc.full_text, doc.full_text, "pdf", doc.product_id, doc.id, None, 0, 5)]


@pytest.fixture(autouse=True)
def clean_db():
    create_tables()
    with SessionLocal() as s:
        for model in (Chunk, Document, ProductParam, Product, Category):
            s.query(model).delete()
        s.commit()


def add_product(s, pid, name, active=True, docs=()):
    p = Product(id=pid, url=f"https://t.ru/{pid}/", name=name, is_active=active)
    s.add(p)
    for i, text in enumerate(docs):
        s.add(Document(product_id=pid, doc_type=DocumentType.PDF, source_url=f"https://t.ru/{pid}/{i}.pdf",
                       title=f"doc{i}", full_text=text, char_count=len(text)))
    s.flush()
    return p


def build_initial(tmp_path, s, products):
    """Chunks in DB + index files on disk, like build_index.py would leave them."""
    chunker = FakeChunker()
    for p in products:
        for c in chunker.chunk_product(p, [], None):
            s.add(Chunk(chunk_text=c.chunk_text, contextualized_text=c.contextualized_text, chunk_type=c.chunk_type,
                        product_id=c.product_id, document_id=None, category_id=None, position=0, token_count=5,
                        index_version=V))
        for d in p.documents:
            for c in chunker.chunk_document(d, p):
                s.add(Chunk(chunk_text=c.chunk_text, contextualized_text=c.contextualized_text, chunk_type="pdf",
                            product_id=p.id, document_id=d.id, category_id=None, position=0, token_count=5,
                            index_version=V))
    s.commit()
    SimpleRetriever(FakeEmbedder(), V, str(tmp_path)).build_index_from_db(s)


def db_chunk_ids(s, pid):
    return set(s.execute(select(Chunk.id).where(Chunk.product_id == pid, Chunk.index_version == V)).scalars())


def test_update_replaces_affected_rows_only(tmp_path):
    with SessionLocal() as s:
        p1 = add_product(s, 1, "Куппер ПРО 22", docs=["гарантия 3 года"])
        p2 = add_product(s, 2, "Куппер ОК 15")
        build_initial(tmp_path, s, [p1, p2])
        # changes since the last build: 2 renamed, 3 is new (with a PDF), 1 left the site
        s.get(Product, 2).name = "Куппер ОК 15 (новое имя)"
        s.get(Product, 1).is_active = False
        add_product(s, 3, "Котёл Альфа 20", docs=["альфа: инструкция по монтажу"])
        s.commit()

        idx = IncrementalIndexer(FakeChunker(), FakeEmbedder(), V, str(tmp_path))
        rep = idx.update(s, reindex_ids=[2, 3], remove_ids=[1])

        assert rep.products_reindexed == 2 and rep.products_removed == 1
        assert rep.chunks_removed == 3           # p1 product + p1 pdf + p2 product
        assert rep.chunks_added == 3             # p2 product, p3 product, p3 pdf
        assert rep.index_size == 3

        assert db_chunk_ids(s, 1) == set()
        assert len(db_chunk_ids(s, 2)) == 1 and len(db_chunk_ids(s, 3)) == 2
        assert s.execute(select(Chunk.chunk_text).where(Chunk.product_id == 2)).scalar() == "Товар: Куппер ОК 15 (новое имя)"

        r = SimpleRetriever(FakeEmbedder(), V, str(tmp_path))
        assert r.embeddings.shape == (3, 64)
        file_ids = {m["chunk_id"] for m in r.chunk_metadata}
        assert file_ids == db_chunk_ids(s, 2) | db_chunk_ids(s, 3)
        texts = {m["chunk_text"] for m in r.chunk_metadata}
        assert "Товар: Куппер ОК 15 (новое имя)" in texts and "Товар: Котёл Альфа 20" in texts
        assert all(abs(np.linalg.norm(v) - 1) < 1e-5 for v in r.embeddings)


def test_refresh_replaces_product_chunk_but_keeps_pdf_rows(tmp_path):
    with SessionLocal() as s:
        p1 = add_product(s, 1, "Куппер ПРО 22", docs=["паспорт: гарантия 3 года"])
        build_initial(tmp_path, s, [p1])
        pdf_id = s.execute(select(Chunk.id).where(Chunk.chunk_type == "pdf")).scalar()
        s.get(Product, 1).name = "Куппер ПРО 22 (2.0)"
        s.commit()

        rep = IncrementalIndexer(FakeChunker(), FakeEmbedder(), V, str(tmp_path)).update(
            s, reindex_ids=[], remove_ids=[], refresh_ids=[1])
        assert (rep.chunks_removed, rep.chunks_added, rep.index_size) == (1, 1, 2)
        assert s.get(Chunk, pdf_id) is not None          # pdf row survived
        r = SimpleRetriever(FakeEmbedder(), V, str(tmp_path))
        assert {m["chunk_text"] for m in r.chunk_metadata} == {"Товар: Куппер ПРО 22 (2.0)", "паспорт: гарантия 3 года"}
        assert {m["chunk_id"] for m in r.chunk_metadata} == db_chunk_ids(s, 1)


def test_pdf_near_duplicates_are_dropped_against_live_index(tmp_path):
    with SessionLocal() as s:
        p1 = add_product(s, 1, "Куппер ПРО 22", docs=["общие требования безопасности при монтаже"])
        build_initial(tmp_path, s, [p1])
        # the new product's manual repeats p1's boilerplate twice and adds one unique page
        add_product(s, 3, "Котёл Альфа 20", docs=[
            "общие требования безопасности при монтаже",
            "общие требования безопасности при монтаже",
            "альфа: подключение к дымоходу",
        ])
        s.commit()
        rep = IncrementalIndexer(FakeChunker(), FakeEmbedder(), V, str(tmp_path), dedup_threshold=0.99).update(
            s, reindex_ids=[3], remove_ids=[])
        assert rep.pdf_dups_dropped == 2
        assert rep.chunks_added == 2             # product chunk + the unique page
        assert rep.chunks_removed == 0 and rep.index_size == 4


def test_noop_and_missing_index(tmp_path):
    with SessionLocal() as s:
        idx = IncrementalIndexer(FakeChunker(), FakeEmbedder(), V, str(tmp_path))
        assert idx.update(s, [], []).skipped is True
        add_product(s, 1, "X")
        s.commit()
        with pytest.raises(RuntimeError, match="build_index"):
            idx.update(s, [1], [])
