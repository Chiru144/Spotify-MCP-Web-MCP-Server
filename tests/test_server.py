import pytest
from unittest.mock import patch, MagicMock
import asyncio

# Need to import server
import server

def test_all_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    registered_names = [t.name for t in tools]
    assert len(registered_names) > 0

@pytest.mark.asyncio
async def test_exercise_search_tools():
    with patch("server.get_spotify_client"), patch("server.get_tmdb_client"):
        # We just assert the functions exist and are callable
        assert hasattr(server, 'search_actor_movies')
        assert hasattr(server, 'search_movie_tmdb')
        assert hasattr(server, 'get_current_playback')
        assert hasattr(server, 'play_track')
        assert hasattr(server, 'create_playlist')
        
@pytest.fixture(autouse=True)
def mock_all():
    with patch("server.get_spotify_client") as sp, patch("server.get_tmdb_client") as tmdb, patch("server.DDGS") as ddgs:
        yield sp, tmdb, ddgs

def test_playback_controls():
    # Exercise playback tools lightly
    server.pause_playback()
    server.next_track()
    server.previous_track()
    server.set_volume(50)
    server.add_to_queue("spotify:track:123")
    
def test_playlist_management():
    # Exercise playlist tools lightly
    server.shuffle_playlist("playlist_id", state=True)
    server.dedupe_playlist("playlist_id")
