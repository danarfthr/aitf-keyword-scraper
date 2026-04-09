import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.keyword import Keyword, KeywordStatus, Source


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Keyword.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_keyword_create(session):
    kw = Keyword(
        keyword="gempa bumi",
        source=Source.GTR,
        rank=1,
    )
    session.add(kw)
    session.commit()
    assert kw.id is not None
    assert kw.status == KeywordStatus.RAW
    assert kw.scraped_at is not None
    assert kw.expand_trigger is None
    assert kw.parent_id is None
    assert kw.ready_for_scraping is False


def test_keyword_status_enum():
    assert KeywordStatus.RAW == "raw"
    assert KeywordStatus.FILTERED == "filtered"
    assert KeywordStatus.FRESH == "fresh"
    assert KeywordStatus.EXPANDED == "expanded"


def test_source_enum():
    assert Source.GTR == "GTR"
    assert Source.T24 == "T24"
