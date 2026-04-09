import pytest
from unittest.mock import patch, MagicMock
from services.openrouter import classify_batch


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")


def test_classify_batch_returns_correct_structure(mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": '{"results":[{"keyword":"gempa","relevant":true},{"keyword":" game","relevant":false}]}'}}]}

    with patch("services.openrouter.requests.post", return_value=mock_response):
        results = classify_batch(["gempa", " game"], model="test-model")
        assert len(results) == 2
        assert results[0].keyword == "gempa"
        assert results[0].relevant is True
        assert results[1].keyword == " game"
        assert results[1].relevant is False


def test_classify_batch_raises_on_missing_api_key():
    import os
    os.environ.pop("OPENROUTER_API_KEY", None)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        classify_batch(["gempa"])
