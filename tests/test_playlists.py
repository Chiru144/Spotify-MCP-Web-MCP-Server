import pytest
from unittest.mock import patch, MagicMock

from tools import playlists

@pytest.fixture(autouse=True)
def mock_clients():
    with patch("tools.core.get_spotify_client") as sp:
        yield sp

def test_playlists_tools(mock_clients):
    sp_mock = mock_clients.return_value
    sp_mock.current_user.return_value = {"id": "test_user"}
    sp_mock.user_playlist_create.return_value = {"id": "new_id"}
    sp_mock.playlist_tracks.return_value = {"items": [], "next": None}
    
    playlists.create_actor_playlist("Tom Hanks")
    playlists.create_playlist("Test Playlist")
    playlists.shuffle_playlist("playlist_id")
    playlists.add_tracks_to_playlist("playlist_id", ["spotify:track:123"])
    playlists.combine_playlists(["id1", "id2"])
    playlists.dedupe_playlist("playlist_id")
    playlists.add_songs_to_playlist("playlist_id", ["spotify:track:123"])
    playlists.add_movie_songs_to_playlist("playlist_id", "Inception")
    playlists.get_user_playlists()
    playlists.update_playlist("playlist_id", name="New Name")
    playlists.get_playlist_tracks("playlist_id")
    playlists.remove_tracks_from_playlist("playlist_id", ["spotify:track:123"])
    playlists.reorder_playlist_by_audio_features("playlist_id")
