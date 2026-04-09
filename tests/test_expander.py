import pytest
from unittest.mock import patch, MagicMock
from services.expander import expand_batch


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")


def test_expand_batch_returns_variants(mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": '{"results":[{"keyword":"gempa","variants":["gempa bumi","gempa hari ini","gempa jakarta"]}]}'}}]}

    with patch("services.expander.requests.post", return_value=mock_response):
        results = expand_batch(["gempa"], model="test-model")
        assert len(results) == 1
        assert "gempa bumi" in results[0].variants


def test_expand_batch_raises_on_missing_api_key():
    import os
    os.environ.pop("OPENROUTER_API_KEY", None)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        expand_batch(["gempa"])
