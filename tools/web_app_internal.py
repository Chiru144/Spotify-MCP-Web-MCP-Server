from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
from tools.core import get_spotify_client
import spotipy

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from pathlib import Path
import threading
WEB_APP_PORT = 8000
_web_app_started = False
_web_app_lock = threading.Lock()

def start_background_web_app(default_port: int = 8000, open_browser: bool = True) -> int:
    """Starts the Soundtrack Curator & Staging Studio FastAPI app in a background daemon thread."""
    global WEB_APP_PORT, _web_app_started
    with _web_app_lock:
        if _web_app_started:
            return WEB_APP_PORT

        import socket
        import sys
        import time
        import webbrowser
        import importlib.util

        def is_port_available(p: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return True
                except OSError:
                    return False

        port = default_port
        while port < default_port + 50 and not is_port_available(port):
            port += 1
        WEB_APP_PORT = port

        def run_server():
            try:
                import uvicorn
                web_server_file = Path(__file__).parent.parent / "mcp-soundtrack-app" / "server.py"
                if not web_server_file.exists():
                    sys.stderr.write(f"[Web App] Could not find web app at {web_server_file}\n")
                    return

                spec = importlib.util.spec_from_file_location("soundtrack_web_app", web_server_file)
                if spec and spec.loader:
                    web_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(web_module)
                    app = getattr(web_module, "app", None)
                    if not app:
                        sys.stderr.write("[Web App] 'app' not found in web server module.\n")
                        return

                    config = uvicorn.Config(
                        app=app,
                        host="127.0.0.1",
                        port=port,
                        log_level="warning",
                        access_log=False
                    )
                    server = uvicorn.Server(config)
                    sys.stderr.write(f"\n[Soundtrack Studio] Web App active at http://127.0.0.1:{port}\n")
                    sys.stderr.flush()
                    server.run()
            except Exception as e:
                sys.stderr.write(f"[Web App] Failed to run web server: {e}\n")
                sys.stderr.flush()

        t = threading.Thread(target=run_server, daemon=True, name="SoundtrackStudioThread")
        t.start()
        _web_app_started = True

        if open_browser:
            def open_browser_delayed():
                time.sleep(1.2)
                try:
                    webbrowser.open(f"http://127.0.0.1:{port}")
                except Exception:
                    pass
            threading.Thread(target=open_browser_delayed, daemon=True).start()

        return WEB_APP_PORT


