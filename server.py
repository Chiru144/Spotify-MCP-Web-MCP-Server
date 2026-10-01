from tools.core import mcp, SPOTIFY_SCOPES, get_spotify_client
from tools import playback, playlists, taste, search, web_app, tmdb_helpers
from tools.web_app_internal import start_background_web_app
import os
import sys

if __name__ == "__main__":
    import threading
    auto_open = os.getenv("OPEN_BROWSER", "true").strip().lower() not in ("0", "false", "no")
    start_background_web_app(default_port=8000, open_browser=auto_open)
    try:
        mcp.run()
    except KeyboardInterrupt:
        pass
