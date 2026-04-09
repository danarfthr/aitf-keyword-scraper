"""
tests/test_integration.py
=========================
End-to-end integration tests for the keyword lifecycle.
"""
import pytest
from fastapi.testclient import TestClient
from database import engine, Base, SessionLocal
from models.keyword import Keyword, Source, KeywordStatus
from api.main import create_app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(Keyword).delete()
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(Keyword).delete()
    db.commit()
    db.close()


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_full_lifecycle(reset_db, client):
    db = SessionLocal()
    for i, kw_text in enumerate(["gempa bumi", " game online", "pemilu 2024"]):
        db.add(Keyword(keyword=kw_text, source=Source.GTR, rank=i+1, status=KeywordStatus.RAW))
    db.commit()
    db.close()

    r = client.post("/keywords/filter")
    assert r.status_code == 200
    result = r.json()
    assert result["total"] == 3
    assert result["filtered"] == 1

    r = client.get("/keywords/fresh")
    assert len(r.json()) == 0


def test_get_keywords_filter(reset_db, client):
    db = SessionLocal()
    db.add(Keyword(keyword="test1", source=Source.GTR, rank=1, status=KeywordStatus.RAW))
    db.add(Keyword(keyword="test2", source=Source.T24, rank=1, status=KeywordStatus.FRESH))
    db.commit()
    db.close()

    r = client.get("/keywords?status=fresh")
    assert len(r.json()) == 1
    assert r.json()[0]["keyword"] == "test2"

    r = client.get("/keywords?source=GTR")
    assert len(r.json()) == 1


def test_delete_keyword(reset_db, client):
    db = SessionLocal()
    kw = Keyword(keyword="delete me", source=Source.GTR, rank=1)
    db.add(kw)
    db.commit()
    kw_id = kw.id
    db.close()

    r = client.delete(f"/keywords/{kw_id}")
    assert r.status_code == 200

    r = client.get("/keywords")
    assert all(k["id"] != kw_id for k in r.json())
