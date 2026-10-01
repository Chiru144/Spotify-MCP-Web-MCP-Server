from typing import Optional, List, Dict, Any
from mcp.types import ToolAnnotations
from tools.core import mcp, get_spotify_client
import spotipy

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def open_soundtrack_studio() -> str:
    """Launch or retrieve the URL for the Soundtrack Curator & Staging Studio web application.
    
    Returns the local web application URL and opens it in your default browser.
    """
    port = start_background_web_app(default_port=8000, open_browser=True)
    url = f"http://127.0.0.1:{port}"
    return f"Soundtrack Curator & Staging Studio is running at {url}. Opened in your default browser!"


