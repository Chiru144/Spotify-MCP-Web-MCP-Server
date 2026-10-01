import pytest
from unittest.mock import patch, MagicMock

from tools import search

@pytest.fixture(autouse=True)
def mock_clients():
    with patch("tools.core.get_spotify_client") as sp, \
         patch("tools.tmdb_helpers.requests.get") as req, \
         patch("tools.tmdb_helpers.DDGS") as ddgs, \
         patch("tools.search.DDGS") as search_ddgs:
        yield sp, req, ddgs, search_ddgs

def test_search_tools(mock_clients):
    sp_mock = mock_clients[0].return_value
    sp_mock.search.return_value = {"tracks": {"items": []}, "artists": {"items": []}, "playlists": {"items": []}}

    search.search_spotify("query")
    search.search_actor_movies("Tom Hanks")
    search.search_movie_tmdb("Inception")
    search.search_duckduckgo("query")
    search.get_movie_songs("Inception")
    search.get_actor_tmdb_profile("Tom Hanks")
