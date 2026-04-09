import pytest
from fastapi.testclient import TestClient
from database import engine, Base
from api.main import create_app


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_keywords_empty(client):
    response = client.get("/keywords")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_keywords_filter_by_status(client):
    response = client.get("/keywords?status=fresh")
    assert response.status_code == 200
