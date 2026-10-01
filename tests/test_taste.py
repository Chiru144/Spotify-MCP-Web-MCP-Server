import pytest
from unittest.mock import patch, MagicMock

from tools import taste

@pytest.fixture(autouse=True)
def mock_clients():
    with patch("tools.core.get_spotify_client") as sp:
        yield sp

def test_taste_tools(mock_clients):
    sp_mock = mock_clients.return_value
    sp_mock.current_user_top_tracks.return_value = {"items": []}
    sp_mock.current_user_top_artists.return_value = {"items": []}
    sp_mock.audio_features.return_value = []
    sp_mock.search.return_value = {"artists": {"items": [{"id": "1", "name": "Artist"}]}}
    sp_mock.artist_related_artists.return_value = {"artists": []}
    sp_mock.current_user_saved_tracks.return_value = {"items": []}

    taste.get_user_top_tracks()
    taste.get_user_top_songs()
    taste.get_user_top_artists()
    taste.get_audio_features(["spotify:track:123"])
    taste.get_artist_network("Artist Name")
    taste.get_saved_tracks()
