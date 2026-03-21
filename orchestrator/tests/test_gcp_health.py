from unittest.mock import patch, MagicMock
import urllib.error

from orchestrator.gcp import GCPManager


def test_health_check_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("orchestrator.gcp.urllib.request.urlopen", return_value=mock_resp):
        assert GCPManager.check_container_health("10.0.0.1") is True


def test_health_check_connection_error():
    with patch("orchestrator.gcp.urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        assert GCPManager.check_container_health("10.0.0.1") is False


def test_health_check_timeout():
    with patch("orchestrator.gcp.urllib.request.urlopen", side_effect=TimeoutError()):
        assert GCPManager.check_container_health("10.0.0.1") is False
