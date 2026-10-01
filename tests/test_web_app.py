import pytest
from unittest.mock import patch, MagicMock

from tools import web_app

@pytest.fixture(autouse=True)
def mock_clients():
    with patch("tools.web_app.start_background_web_app") as bg_web:
        yield bg_web

def test_web_app_tools():
    web_app.open_soundtrack_studio()
