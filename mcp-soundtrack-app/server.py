import os
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials

# Load environment variables (check local folder and parent folder)
BASE_DIR = Path(__file__).parent
env_local = BASE_DIR / ".env"
env_parent = BASE_DIR.parent / ".env"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
elif env_parent.exists():
    load_dotenv(dotenv_path=env_parent)
else:
    load_dotenv()

recently_modified_counts = {}

app = FastAPI(title="Soundtrack Curator & Staging Studio")

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN")

# Helper to get valid non-placeholder credentials
def _get_credential(key1: str, key2: str) -> str:
    v1 = os.getenv(key1, "").strip()
    v2 = os.getenv(key2, "").strip()
    if v1 and "your_" not in v1 and not v1.startswith("your_"):
        return v1
    if v2 and "your_" not in v2 and not v2.startswith("your_"):
        return v2
    return v1 or v2

SPOTIFY_CLIENT_ID = _get_credential("SPOTIFY_CLIENT_ID", "SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = _get_credential("SPOTIFY_CLIENT_SECRET", "SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI") or os.getenv("SPOTIPY_REDIRECT_URI") or "http://127.0.0.1:8888/callback"

SCOPES = [
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "user-library-modify",
    "user-read-private",
    "user-read-email",
]

# Client Credentials client for public search operations (Never blocks or prompts for browser OAuth login)
public_sp = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        public_sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET
            ),
            requests_timeout=5
        )
    except Exception as e:
        print(f"Warning: Could not initialize public Spotify client: {e}")

import http.server
import socketserver
import threading
import urllib.parse

# User OAuth Manager for authenticated actions (using shared root cache)
_cache_file = BASE_DIR.parent / ".spotipyoauthcache"
if not _cache_file.exists() and (BASE_DIR / ".spotipyoauthcache").exists():
    _cache_file = BASE_DIR / ".spotipyoauthcache"

oauth_manager = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=" ".join(SCOPES),
    cache_path=str(_cache_file),
    open_browser=True
)


class OAuth8888Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence stderr to keep console clean

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        error = qs.get("error", [None])[0]

        if code:
            try:
                oauth_manager.get_access_token(code)
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:8000/?connected=true")
                self.end_headers()
                return
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = f"""<!DOCTYPE html>
<html>
<head><title>Spotify Authorization</title><meta http-equiv="refresh" content="2;url=http://127.0.0.1:8000/?connected=true"></head>
<body style="background:#090c10;color:#fff;font-family:sans-serif;padding:50px;text-align:center;">
  <h2 style="color:#1db954;">Spotify Authorization Handled!</h2>
  <p>{e}</p>
  <p><a href="http://127.0.0.1:8000/?connected=true" style="color:#1db954;font-size:18px;">Return to Soundtrack Curator Studio</a></p>
</body>
</html>"""
                self.wfile.write(html.encode("utf-8"))
                return

        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:8000/?auth_error={error or 'cancelled'}")
        self.end_headers()


_oauth_server_started = False
def start_oauth_callback_server(port: int = 8888):
    global _oauth_server_started
    if _oauth_server_started:
        return
    try:
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        server_8888 = ReusableTCPServer(("127.0.0.1", port), OAuth8888Handler)
        t = threading.Thread(target=server_8888.serve_forever, daemon=True, name="OAuth8888Listener")
        t.start()
        _oauth_server_started = True
        print(f"[OAuth Helper] Callback listener active on http://127.0.0.1:{port}/callback")
    except Exception as e:
        print(f"[OAuth Helper] Note: Port {port} listener not started: {e}")

# Automatically start background listener on port 8888
start_oauth_callback_server(8888)


def _get_valid_user_client() -> Optional[spotipy.Spotify]:
    """Returns authenticated spotipy.Spotify if valid token exists in cache, else None (never blocks)."""
    token_info = oauth_manager.cache_handler.get_cached_token()
    if not token_info:
        return None
    if oauth_manager.is_token_expired(token_info):
        try:
            token_info = oauth_manager.refresh_access_token(token_info.get("refresh_token"))
        except Exception:
            token_info = None
    if token_info and token_info.get("access_token"):
        return spotipy.Spotify(auth=token_info["access_token"])
    return None





def _get_tmdb_headers_and_params(extra_params: dict = None) -> tuple[dict, dict]:
    params = extra_params or {}
    headers = {"accept": "application/json"}
    if TMDB_READ_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    elif TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY
    return headers, params


def fetch_soundtrack_tracks(movie_title: str, language_name: str = None) -> list[dict]:
    """Searches Spotify for movie soundtrack tracks using client credentials or user client."""
    client = _get_valid_user_client() or public_sp
    if not client:
        return []

    try:
        clean_title = movie_title.strip()
        search_title = clean_title
        if language_name:
            search_title = f"{clean_title} {language_name}"
            
        import difflib
        def is_fuzzy_match(movie: str, target: str) -> bool:
            movie = movie.lower()
            target = target.lower()
            if movie in target: return True
            for m_word in movie.split():
                if len(m_word) < 4: continue
                for t_word in target.split():
                    if difflib.SequenceMatcher(None, m_word, t_word).ratio() > 0.8:
                        return True
            return False
            
        # Strategy 1: Search for album with "soundtrack" or "OST"
        albums = []
        for q in [f"album:{search_title} soundtrack", f"{search_title} soundtrack", f"{search_title} ost", search_title]:
            res = client.search(q=q, type="album", limit=3)
            found = res.get("albums", {}).get("items", [])
            for album in found:
                if is_fuzzy_match(clean_title, album.get("name", "")):
                    albums = [album]
                    break
            if albums:
                break

        if albums:
            album = albums[0]
            album_id = album["id"]
            album_name = album.get("name", clean_title)
            album_cover = album.get("images", [{}])[0].get("url") if album.get("images") else None
            album_release = album.get("release_date", "")

            tracks_res = client.album_tracks(album_id, limit=20)
            formatted = []
            for t in tracks_res.get("items", []):
                artists = ", ".join(a.get("name", "Unknown") for a in t.get("artists", []))
                artist_ids = [a.get("id") for a in t.get("artists", []) if a.get("id")]
                formatted.append({
                    "name": t.get("name"),
                    "artist": artists,
                    "artist_ids": artist_ids,
                    "uri": t.get("uri"),
                    "duration_ms": t.get("duration_ms", 0),
                    "popularity": 50,
                    "release_date": album_release,
                    "spotify_url": t.get("external_urls", {}).get("spotify"),
                    "album_name": album_name,
                    "album_cover": album_cover
                })
            if formatted:
                return formatted

        # Strategy 2: Fallback to direct track search for movie songs
        fallback_queries = [f"{search_title} soundtrack", f"{search_title} theme", search_title]
        tracks_list = []
        seen_uris = set()
        for fq in fallback_queries:
            fallback = client.search(q=fq, type="track", limit=10)
            for t in fallback.get("tracks", {}).get("items", []):
                uri = t.get("uri")
                track_name = t.get("name", "").lower()
                album_name = t.get("album", {}).get("name", "").lower()
                
                # Stricter matching with fuzzy logic
                if not is_fuzzy_match(clean_title, track_name) and not is_fuzzy_match(clean_title, album_name):
                    continue
                    
                if uri and uri not in seen_uris:
                    seen_uris.add(uri)
                    artist_ids = [a.get("id") for a in t.get("artists", []) if a.get("id")]
                    tracks_list.append({
                        "name": t.get("name"),
                        "artist": ", ".join(a.get("name", "Unknown") for a in t.get("artists", [])),
                        "artist_ids": artist_ids,
                        "uri": uri,
                        "duration_ms": t.get("duration_ms", 0),
                        "popularity": t.get("popularity", 0),
                        "release_date": t.get("album", {}).get("release_date", ""),
                        "spotify_url": t.get("external_urls", {}).get("spotify"),
                        "album_name": t.get("album", {}).get("name", clean_title),
                        "album_cover": t.get("album", {}).get("images", [{}])[0].get("url") if t.get("album", {}).get("images") else None
                    })
            if len(tracks_list) >= 8:
                break
        return tracks_list
    except Exception as e:
        print(f"Error fetching soundtrack for {movie_title}: {e}")
        return []


@app.get("/api/movie/tracks")
def get_movie_soundtracks(
    movie_title: str = Query(..., description="Movie Title"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Fetches official soundtrack tracks on demand when a movie card is clicked."""
    lang_map = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam"}
    tracks = fetch_soundtrack_tracks(movie_title, language_name=lang_map.get(lang))
    return {"movie_title": movie_title, "tracks": tracks}


# =====================================================================
# API Endpoints
# =====================================================================

@app.get("/login")
def login_redirect():
    """Redirect to Spotify OAuth authorize page."""
    auth_url = oauth_manager.get_authorize_url()
    return RedirectResponse(auth_url)


@app.get("/callback")
def oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    """Handle callback from Spotify OAuth redirect."""
    if error:
        return RedirectResponse(f"/?auth_error={error}")
    if code:
        try:
            oauth_manager.get_access_token(code)
            return RedirectResponse("/?connected=true")
        except Exception as e:
            return RedirectResponse(f"/?auth_error={urllib.parse.quote(str(e))}")
    return RedirectResponse("/")


class CodeExchangeRequest(BaseModel):
    code_or_url: str


@app.post("/api/auth/exchange_code")
def exchange_oauth_code(payload: CodeExchangeRequest):
    """Manual or fallback endpoint to exchange a redirect URL or code for a Spotify token."""
    raw = payload.code_or_url.strip()
    if not raw:
        return {"success": False, "error": "No code or URL provided."}
    
    code = raw
    if "code=" in raw:
        try:
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [raw])[0]
        except Exception:
            code = raw
            
    try:
        token_info = oauth_manager.get_access_token(code)
        if token_info:
            user_client = _get_valid_user_client()
            user_data = user_client.me() if user_client else {}
            return {
                "success": True,
                "display_name": user_data.get("display_name") or user_data.get("id", "Spotify User"),
                "id": user_data.get("id")
            }
        return {"success": False, "error": "Could not validate access token."}
    except Exception as e:
        return {"success": False, "error": str(e)}



@app.get("/api/me")
def get_user_profile():
    """Returns connected Spotify account info without blocking on terminal stdin."""
    try:
        user_client = _get_valid_user_client()
        if not user_client:
            auth_url = oauth_manager.get_authorize_url()
            return {"authenticated": False, "auth_url": auth_url}

        user = user_client.me()
        token_info = oauth_manager.cache_handler.get_cached_token()
        token_scope = token_info.get("scope", "") if token_info else ""
        has_playlist_read = "playlist-read-private" in token_scope
        return {
            "authenticated": True,
            "id": user.get("id"),
            "display_name": user.get("display_name") or user.get("id"),
            "images": user.get("images", []),
            "product": user.get("product", "unknown"),
            "has_playlist_read": has_playlist_read,
            "auth_url": oauth_manager.get_authorize_url() if not has_playlist_read else None
        }
    except Exception as e:
        return {"authenticated": False, "error": str(e), "auth_url": oauth_manager.get_authorize_url()}


@app.get("/api/search/movies")
def search_movies_only(
    query: str = Query(..., description="Movie title"),
    limit: int = Query(25, description="Number of items to show"),
    sort_by: str = Query("date_desc", description="Sort rank: date_desc, date_asc, popularity, rating, title"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Dedicated Movie Search: searches TMDB specifically for movies and loads soundtrack songs."""
    lang_map = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam"}
    lang_name = lang_map.get(lang)
    headers, params = _get_tmdb_headers_and_params({
        "query": query,
        "include_adult": "false",
        "language": "en-US",
        "page": "1"
    })
    
    movie_search_url = "https://api.tmdb.org/3/search/movie"
    movies_raw = []
    try:
        m_res = requests.get(movie_search_url, headers=headers, params=params, timeout=4).json()
        movies_raw = m_res.get("results", [])
    except Exception as e:
        print(f"Movie search error: {e}")
        
    if not movies_raw:
        # Fallback if TMDB is blocked/down
        movies_raw = [{
            "title": query.title(),
            "release_date": "N/A",
            "overview": "Could not connect to the movie database, but searching Spotify directly for soundtracks...",
            "popularity": 100,
            "vote_average": 0
        }]

    # Sorting
    if sort_by == "date_desc":
        movies_raw.sort(key=lambda x: x.get("release_date") or "0000-00-00", reverse=True)
    elif sort_by == "date_asc":
        movies_raw.sort(key=lambda x: x.get("release_date") or "9999-99-99")
    elif sort_by == "popularity":
        movies_raw.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    elif sort_by == "rating":
        movies_raw.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
    elif sort_by == "title":
        movies_raw.sort(key=lambda x: (x.get("title") or "").lower())

    total_found = len(movies_raw)
    selection = movies_raw[:limit]

    output = []
    soundtrack_fetch_limit = min(limit, 25)
    total_songs_count = 0
    for idx, m in enumerate(selection):
        title = m.get("title")
        release_date = m.get("release_date")
        overview = m.get("overview", "")
        poster = f"https://image.tmdb.org/t/p/w300{m.get('poster_path')}" if m.get("poster_path") else None
        backdrop = f"https://image.tmdb.org/t/p/w780{m.get('backdrop_path')}" if m.get("backdrop_path") else None
        vote_average = m.get("vote_average", 0)
        popularity = m.get("popularity", 0)

        songs = fetch_soundtrack_tracks(title, language_name=lang_name) if idx < soundtrack_fetch_limit else []
        total_songs_count += len(songs)

        output.append({
            "title": title,
            "release_date": release_date,
            "overview": overview[:180] + "..." if len(overview) > 180 else overview,
            "character": "",
            "vote_average": round(vote_average, 1),
            "popularity": round(popularity, 1),
            "poster": poster,
            "backdrop": backdrop,
            "tracks": songs,
            "song_count": len(songs)
        })

    return {
        "mode": "movies",
        "search_type": "movie",
        "query": query,
        "display_name": query,
        "total_results": total_found,
        "shown": len(output),
        "total_songs": total_songs_count,
        "movies": output
    }


@app.get("/api/search/actors")
def search_actors_only(
    query: str = Query(..., description="Actor or actress name"),
    limit: int = Query(25, description="Number of items to show"),
    sort_by: str = Query("popularity", description="Sort rank: popularity, date_desc, date_asc, rating, title"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Dedicated Actor Search: searches TMDB for actors, their career filmography, and soundtrack songs."""
    lang_map = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam"}
    lang_name = lang_map.get(lang)
    
    import re
    clean_query = query.lower()
    for word in ["kannada", "telugu", "tamil", "hindi", "malayalam", "english", "bollywood", "tollywood", "kollywood", "sandalwood", "actor", "actress", "singer", "director"]:
        clean_query = re.sub(rf"\b{word}\b", "", clean_query)
    clean_query = clean_query.strip() or query

    headers, params = _get_tmdb_headers_and_params({
        "query": clean_query,
        "include_adult": "false",
        "language": "en-US",
        "page": "1"
    })
    
    person_search_url = "https://api.tmdb.org/3/search/person"
    actor_data = None
    movies_raw = []

    try:
        person_res = requests.get(person_search_url, headers=headers, params=params, timeout=4).json()
        person_results = person_res.get("results", [])
        
        if person_results:
            person = person_results[0]
            person_id = person["id"]
            actor_name = person.get("name", query)
            
            # Fetch profile details
            p_headers, p_params = _get_tmdb_headers_and_params()
            try:
                prof_res = requests.get(f"https://api.tmdb.org/3/person/{person_id}", headers=p_headers, params=p_params, timeout=4).json()
            except Exception:
                prof_res = person

            credits_url = f"https://api.tmdb.org/3/person/{person_id}/movie_credits"
            credits = requests.get(credits_url, headers=p_headers, params=p_params, timeout=4).json()
            cast = credits.get("cast", [])
            if lang:
                movies_raw = [m for m in cast if m.get("title") and m.get("original_language") == lang]
            else:
                movies_raw = [m for m in cast if m.get("title")]

            actor_data = {
                "id": person_id,
                "name": actor_name,
                "biography": prof_res.get("biography", ""),
                "birthday": prof_res.get("birthday"),
                "place_of_birth": prof_res.get("place_of_birth"),
                "popularity": prof_res.get("popularity", person.get("popularity", 0)),
                "profile_path": f"https://image.tmdb.org/t/p/w300{person.get('profile_path')}" if person.get("profile_path") else None,
                "known_for_department": prof_res.get("known_for_department", "Acting")
            }
    except Exception as e:
        print(f"Actor search error: {e}")

    if not movies_raw:
        # Fallback if TMDB is blocked
        movies_raw = [{
            "title": f"{query.title()} Movies",
            "release_date": "N/A",
            "overview": "Could not connect to the movie database, but searching Spotify directly for soundtracks...",
            "popularity": 100,
            "vote_average": 0
        }]
        actor_data = {"name": query.title()}

    # Sorting
    if sort_by == "popularity":
        movies_raw.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    elif sort_by == "date_desc":
        movies_raw.sort(key=lambda x: x.get("release_date") or "0000-00-00", reverse=True)
    elif sort_by == "date_asc":
        movies_raw.sort(key=lambda x: x.get("release_date") or "9999-99-99")
    elif sort_by == "rating":
        movies_raw.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
    elif sort_by == "title":
        movies_raw.sort(key=lambda x: (x.get("title") or "").lower())

    total_found = len(movies_raw)
    selection = movies_raw[:limit]

    output = []
    soundtrack_fetch_limit = min(limit, 25)
    total_songs_count = 0
    for idx, m in enumerate(selection):
        title = m.get("title")
        release_date = m.get("release_date")
        overview = m.get("overview", "")
        poster = f"https://image.tmdb.org/t/p/w300{m.get('poster_path')}" if m.get("poster_path") else None
        backdrop = f"https://image.tmdb.org/t/p/w780{m.get('backdrop_path')}" if m.get("backdrop_path") else None
        character = m.get("character", "")
        vote_average = m.get("vote_average", 0)
        popularity = m.get("popularity", 0)

        songs = fetch_soundtrack_tracks(title, language_name=lang_name) if idx < soundtrack_fetch_limit else []
        total_songs_count += len(songs)

        output.append({
            "title": title,
            "release_date": release_date,
            "overview": overview[:180] + "..." if len(overview) > 180 else overview,
            "character": character,
            "vote_average": round(vote_average, 1),
            "popularity": round(popularity, 1),
            "poster": poster,
            "backdrop": backdrop,
            "tracks": songs,
            "song_count": len(songs)
        })

    return {
        "mode": "actors",
        "search_type": "actor",
        "query": query,
        "display_name": actor_data["name"] if actor_data else query,
        "actor": actor_data,
        "total_results": total_found,
        "shown": len(output),
        "total_songs": total_songs_count,
        "movies": output
    }


@app.get("/api/search")
def search_movies(
    query: str = Query(..., description="Actor name or movie title"),
    limit: int = Query(25, description="Number of items to show"),
    sort_by: str = Query("date_desc", description="Sort rank: date_desc, date_asc, popularity, rating, title"),
    search_type: Optional[str] = Query(None, description="'movie' or 'actor'"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Unified search endpoint routing to movie or actor search."""
    if search_type == "movie":
        return search_movies_only(query=query, limit=limit, sort_by=sort_by, lang=lang)
    if search_type == "actor":
        return search_actors_only(query=query, limit=limit, sort_by=sort_by, lang=lang)
    
    # Auto-detection fallback
    headers, params = _get_tmdb_headers_and_params({"query": query})
    try:
        person_res = requests.get("https://api.tmdb.org/3/search/person", headers=headers, params=params, timeout=2).json()
        person_results = person_res.get("results", [])
        if person_results and (person_results[0].get("name", "").lower() in query.lower() or query.lower() in person_results[0].get("name", "").lower()):
            return search_actors_only(query=query, limit=limit, sort_by=sort_by, lang=lang)
    except Exception:
        pass
    return search_movies_only(query=query, limit=limit, sort_by=sort_by, lang=lang)


@app.get("/api/search/songs")
def search_songs(
    query: str = Query(..., description="Song title, soundtrack, or artist"),
    limit: int = Query(25, description="Number of songs to show: 10, 25, 50, 100, 200, 500, 1000"),
    sort_by: str = Query("popularity", description="Sort rank: popularity, date_desc, date_asc, duration_desc, duration_asc, name, artist"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Direct Spotify Song & Soundtrack Search with limit and ranking filters."""
    lang_map = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam"}
    if lang and lang in lang_map:
        query = f"{query} {lang_map[lang]}"
        
    client = public_sp
    if not client:
        return {"error": "Spotify client not configured", "songs": []}

    try:
        fetch_limit = min(limit, 50)
        all_tracks = []

        res = client.search(q=query, type="track", limit=fetch_limit, offset=0)
        items = res.get("tracks", {}).get("items", [])
        total_available = res.get("tracks", {}).get("total", len(items))
        all_tracks.extend(items)

        max_batch = min(limit, 200, total_available)
        offset = fetch_limit
        while offset < max_batch and len(all_tracks) < limit:
            batch_size = min(50, limit - len(all_tracks))
            batch_res = client.search(q=query, type="track", limit=batch_size, offset=offset)
            batch_items = batch_res.get("tracks", {}).get("items", [])
            if not batch_items:
                break
            all_tracks.extend(batch_items)
            offset += len(batch_items)

        formatted = []
        for t in all_tracks:
            album = t.get("album", {})
            artists = t.get("artists", [])
            artist_names = ", ".join([a.get("name", "") for a in artists]) or "Unknown"
            artist_ids = [a.get("id") for a in artists if a.get("id")]

            formatted.append({
                "id": t.get("id"),
                "name": t.get("name"),
                "artist": artist_names,
                "artist_ids": artist_ids,
                "album_name": album.get("name", ""),
                "album_cover": album.get("images", [{}])[0].get("url") if album.get("images") else None,
                "release_date": album.get("release_date", ""),
                "popularity": t.get("popularity", 0),
                "duration_ms": t.get("duration_ms", 0),
                "uri": t.get("uri"),
                "spotify_url": t.get("external_urls", {}).get("spotify"),
                "preview_url": t.get("preview_url")
            })

        if sort_by == "popularity":
            formatted.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        elif sort_by == "date_desc":
            formatted.sort(key=lambda x: x.get("release_date") or "0000", reverse=True)
        elif sort_by == "date_asc":
            formatted.sort(key=lambda x: x.get("release_date") or "9999")
        elif sort_by == "duration_desc":
            formatted.sort(key=lambda x: x.get("duration_ms", 0), reverse=True)
        elif sort_by == "duration_asc":
            formatted.sort(key=lambda x: x.get("duration_ms", 0))
        elif sort_by == "name":
            formatted.sort(key=lambda x: x.get("name", "").lower())
        elif sort_by == "artist":
            formatted.sort(key=lambda x: x.get("artist", "").lower())

        
        return {
            "mode": "songs",
            "query": query,
            "total_results": total_available,
            "shown": len(formatted),
            "songs": formatted
        }
    except Exception as e:
        print(f"Song search error: {e}")
        return {"error": str(e), "songs": [], "total_results": 0}


@app.get("/api/search/track")
def search_direct_track(query: str = Query(..., description="Track search query")):
    """Quick lookup to add custom songs into the Send Box."""
    client = public_sp
    if not client:
        return {"error": "Spotify client not initialized", "tracks": []}

    try:
        res = client.search(q=query, type="track", limit=6)
        items = res.get("tracks", {}).get("items", [])
        results = []
        for t in items:
            results.append({
                "name": t.get("name"),
                "artist": t.get("artists", [{}])[0].get("name", "Unknown"),
                "uri": t.get("uri"),
                "album_name": t.get("album", {}).get("name", ""),
                "album_cover": t.get("album", {}).get("images", [{}])[0].get("url") if t.get("album", {}).get("images") else None,
                "spotify_url": t.get("external_urls", {}).get("spotify"),
            })
        return {"tracks": results}
    except Exception as e:
        return {"error": str(e), "tracks": []}


@app.get("/api/search/singers")
def search_singers(
    query: str = Query(..., description="Singer or music artist name"),
    limit: int = Query(25, description="Number of tracks to show"),
    sort_by: str = Query("popularity", description="Sort order: popularity, date_desc, date_asc, name"),
    lang: Optional[str] = Query(None, description="Language filter")
):
    """Searches for singers/artists and returns their discography and songs."""
    lang_map = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam"}
    if lang and lang in lang_map:
        query = f"{query} {lang_map[lang]}"
    client = _get_valid_user_client() or public_sp
    if not client:
        return {"error": "Spotify credentials not configured", "artist": None, "tracks": []}
    
    try:
        # Search for artist
        artist_res = client.search(q=query, type="artist", limit=3)
        artists = artist_res.get("artists", {}).get("items", [])
        top_artist = artists[0] if artists else None

        # Search tracks by artist
        search_q = f"artist:{top_artist['name']}" if top_artist else f"artist:{query}"
        track_res = client.search(q=search_q, type="track", limit=min(limit, 50))
        items = track_res.get("tracks", {}).get("items", [])
        if not items:
            track_res = client.search(q=query, type="track", limit=min(limit, 50))
            items = track_res.get("tracks", {}).get("items", [])

        formatted = []
        for t in items:
            formatted.append({
                "name": t.get("name"),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])) or "Unknown",
                "uri": t.get("uri"),
                "duration_ms": t.get("duration_ms", 0),
                "popularity": t.get("popularity", 50),
                "release_date": t.get("album", {}).get("release_date", ""),
                "spotify_url": t.get("external_urls", {}).get("spotify"),
                "album_name": t.get("album", {}).get("name", ""),
                "album_cover": t.get("album", {}).get("images", [{}])[0].get("url") if t.get("album", {}).get("images") else None,
                "singer_name": top_artist["name"] if top_artist else query
            })

        if sort_by == "popularity":
            formatted.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        elif sort_by == "date_desc":
            formatted.sort(key=lambda x: x.get("release_date") or "0000", reverse=True)
        elif sort_by == "date_asc":
            formatted.sort(key=lambda x: x.get("release_date") or "9999")
        elif sort_by == "name":
            formatted.sort(key=lambda x: (x.get("name") or "").lower())

        artist_data = None
        if top_artist:
            artist_data = {
                "name": top_artist.get("name"),
                "id": top_artist.get("id"),
                "image": top_artist.get("images", [{}])[0].get("url") if top_artist.get("images") else None,
                "genres": top_artist.get("genres", [])[:4],
                "followers": top_artist.get("followers", {}).get("total", 0),
                "popularity": top_artist.get("popularity", 0),
                "spotify_url": top_artist.get("external_urls", {}).get("spotify")
            }

        return {
            "mode": "singers",
            "query": query,
            "artist": artist_data,
            "total_results": len(formatted),
            "tracks": formatted[:limit]
        }
    except Exception as e:
        return {"error": str(e), "artist": None, "tracks": [], "total_results": 0}


class PlaylistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = "Curated with Soundtrack Curator"
    public: Optional[bool] = False
    track_uris: List[str]


@app.post("/api/playlist/create")
def create_playlist(payload: PlaylistCreateRequest):
    """Creates a Spotify playlist with the chosen name and staged tracks."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required. Click 'Connect Spotify' in the top right to link your account."
        }

    try:
        playlist_name = payload.name.strip() or "Curated Soundtracks"
        # Use current_user_playlist_create (POST /v1/me/playlists) which is the modern Spotify endpoint
        playlist = user_client.current_user_playlist_create(
            name=playlist_name,
            public=bool(payload.public),
            description=payload.description or "Curated with Soundtrack Curator Studio"
        )
        valid_uris = [u for u in payload.track_uris if u and u.startswith("spotify:track:")]
        if valid_uris:
            for i in range(0, len(valid_uris), 100):
                user_client.playlist_add_items(playlist_id=playlist["id"], items=valid_uris[i:i+100])

        return {
            "success": True,
            "playlist_id": playlist["id"],
            "playlist_name": playlist.get("name"),
            "playlist_url": playlist.get("external_urls", {}).get("spotify"),
            "track_count": len(valid_uris),
            "song_count": len(valid_uris)
        }
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "Insufficient client scope" in err_msg:
            return {
                "success": False,
                "need_auth": True,
                "auth_url": oauth_manager.get_authorize_url(),
                "error": "Spotify permission issue (403). Click 'Connect Spotify' in the top right to grant playlist creation permissions."
            }
        return {"success": False, "error": str(e)}


@app.get("/api/user/playlists")
def get_user_playlists():
    """Returns the authenticated user's Spotify playlists for fetching/appending."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "authenticated": False,
            "playlists": [],
            "error": "Spotify authorization required."
        }
    try:
        current_user = user_client.me()
        current_user_id = current_user.get("id")
        
        playlists_data = user_client.current_user_playlists(limit=50)
        items = playlists_data.get("items", [])
        results = []
        for p in items:
            if not p:
                continue
            
            # Filter to only show playlists owned by the user (not followed/restricted ones)
            owner_id = p.get("owner", {}).get("id")
            if owner_id != current_user_id:
                continue
                
            images = p.get("images") or []
            cover = images[0].get("url") if images else None
            
            pid = p.get("id")
            total = p.get("tracks", p.get("items", {})).get("total", 0)
            if pid in recently_modified_counts:
                total = recently_modified_counts[pid]
                
            results.append({
                "id": pid,
                "name": p.get("name", "Untitled Playlist"),
                "description": p.get("description", ""),
                "total_tracks": total,
                "cover_url": cover,
                "owner": p.get("owner", {}).get("display_name") or p.get("owner", {}).get("id", "Unknown"),
                "spotify_url": p.get("external_urls", {}).get("spotify"),
                "uri": p.get("uri")
            })
        return {"authenticated": True, "playlists": results}
    except Exception as e:
        err_msg = str(e)
        if "Insufficient client scope" in err_msg or "403" in err_msg:
            return {
                "authenticated": True,
                "need_scope": True,
                "auth_url": oauth_manager.get_authorize_url(),
                "playlists": [],
                "error": "Additional Spotify permissions needed to view your playlists. Click 'Connect Spotify' to grant playlist reading permissions."
            }
        return {"authenticated": True, "playlists": [], "error": str(e)}


@app.get("/api/playlist/fetch")
def fetch_playlist_tracks(query: str = Query(..., description="Spotify Playlist URL, URI, or ID")):
    """Fetches full track list and details for any Spotify playlist."""
    cleaned = query.strip()
    playlist_id = cleaned
    if "playlist/" in cleaned:
        playlist_id = cleaned.split("playlist/")[1]
    elif "spotify:playlist:" in cleaned:
        playlist_id = cleaned.split("spotify:playlist:")[1]
    
    playlist_id = playlist_id.split("?")[0].split("/")[0]

    client = _get_valid_user_client() or public_sp
    if not client:
        return {"success": False, "error": "Spotify credentials not configured."}

    try:
        pl = client.playlist(playlist_id)
        name = pl.get("name", "Spotify Playlist")
        desc = pl.get("description", "")
        images = pl.get("images") or []
        cover = images[0].get("url") if images else None
        owner = pl.get("owner", {}).get("display_name") or pl.get("owner", {}).get("id", "Unknown")
        spotify_url = pl.get("external_urls", {}).get("spotify")
        total_tracks = pl.get("tracks", pl.get("items", {})).get("total", 0)

        tracks = []
        try:
            items_res = client.playlist_items(playlist_id, limit=100)
            while items_res:
                items = items_res.get("items", [])
                for it in items:
                    t = it.get("track") or it.get("item")
                    if not t or not t.get("uri"):
                        continue
                    artists = ", ".join(a.get("name", "Unknown") for a in t.get("artists", []))
                    album_imgs = t.get("album", {}).get("images") or []
                    track_cover = album_imgs[0].get("url") if album_imgs else cover
                    tracks.append({
                        "name": t.get("name"),
                        "artist": artists,
                        "uri": t.get("uri"),
                        "duration_ms": t.get("duration_ms", 0),
                        "popularity": t.get("popularity", 50),
                        "album_name": t.get("album", {}).get("name", ""),
                        "album_cover": track_cover,
                        "spotify_url": t.get("external_urls", {}).get("spotify"),
                        "source_playlist": name
                    })
                if items_res.get("next"):
                    items_res = client.next(items_res)
                else:
                    break
        except Exception as te:
            print(f"Error reading playlist items: {te}")

        return {
            "success": True,
            "playlist": {
                "id": playlist_id,
                "name": name,
                "description": desc,
                "cover_url": cover,
                "owner": owner,
                "spotify_url": spotify_url,
                "track_count": total_tracks if total_tracks > 0 else len(tracks)
            },
            "tracks": tracks
        }
    except Exception as e:
        return {"success": False, "error": f"Could not fetch playlist: {str(e)}"}


class PlaylistAppendRequest(BaseModel):
    playlist_id: str
    track_uris: List[str]


@app.post("/api/playlist/append")
def append_to_playlist(payload: PlaylistAppendRequest):
    """Appends staged tracks to an existing Spotify playlist."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required. Click 'Connect Spotify' in the top right to link your account."
        }

    try:
        pid = payload.playlist_id.strip()
        if "playlist/" in pid:
            pid = pid.split("playlist/")[1]
        elif "spotify:playlist:" in pid:
            pid = pid.split("spotify:playlist:")[1]
            
        pid = pid.split("?")[0].split("/")[0]

        valid_uris = [u for u in payload.track_uris if u and u.startswith("spotify:track:")]
        if not valid_uris:
            return {"success": False, "error": "No valid track URIs provided."}

        for i in range(0, len(valid_uris), 100):
            user_client.playlist_add_items(playlist_id=pid, items=valid_uris[i:i+100])

        return {
            "success": True,
            "playlist_id": pid,
            "added_count": len(valid_uris),
            "song_count": len(valid_uris),
            "message": f"Added {len(valid_uris)} song(s) to playlist."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


from typing import Optional

class PlaylistShuffleRequest(BaseModel):
    playlist_id: str
    in_place: bool = False
    new_name: Optional[str] = None


@app.post("/api/playlist/shuffle")
def shuffle_playlist(payload: PlaylistShuffleRequest):
    """Mixes and shuffles all songs in a Spotify playlist into a completely new random order."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required. Click 'Connect Spotify' in the top right to link your account."
        }

    try:
        pid = payload.playlist_id.strip()
        if "playlist/" in pid:
            pid = pid.split("playlist/")[1]
        elif "spotify:playlist:" in pid:
            pid = pid.split("spotify:playlist:")[1]
            
        pid = pid.split("?")[0].split("/")[0]

        # Fetch all songs (handle paging)
        items = []
        try:
            res = user_client.playlist_items(pid, limit=100)
            while res:
                items.extend(res.get("items", []))
                if res.get("next"):
                    res = user_client.next(res)
                else:
                    break
        except Exception as e:
            if "403" in str(e):
                try:
                    # Fallback for public playlists that user_client might fail on (e.g., token scope issues)
                    from spotipy.oauth2 import SpotifyClientCredentials
                    client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
                    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
                    app_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                    res = app_client.playlist_items(pid, limit=100)
                    while res:
                        items.extend(res.get("items", []))
                        if res.get("next"):
                            res = app_client.next(res)
                        else:
                            break
                except Exception as app_e:
                    return {"success": False, "error": "Spotify refused access (403 Forbidden). This playlist is either private to another user or completely restricted."}
            else:
                raise e

        valid_tracks = [it.get("track") or it.get("item") for it in items if (it.get("track") or it.get("item")) and (it.get("track") or it.get("item")).get("uri")]
        if not valid_tracks:
            return {"success": False, "error": "No songs found in this playlist to shuffle."}

        total_songs = len(valid_tracks)
        # Mix/shuffle all the songs into a different order
        shuffled = list(valid_tracks)
        random.shuffle(shuffled)

        try:
            playlist = user_client.playlist(pid)
        except Exception as e:
            if "403" in str(e):
                from spotipy.oauth2 import SpotifyClientCredentials
                client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
                client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
                app_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                playlist = app_client.playlist(pid)
            else:
                raise e
        
        original_name = playlist.get("name", "Shuffled Playlist")
        
        shuffled_uris = [t["uri"] for t in shuffled if t.get("uri", "").startswith("spotify:track:")]
        if not shuffled_uris:
            return {"success": False, "error": "No valid tracks to shuffle."}
            
        if payload.in_place:
            current_user = user_client.me().get("id")
            owner_id = playlist.get("owner", {}).get("id")
            if current_user != owner_id:
                return {"success": False, "error": "You cannot shuffle a playlist in-place if you are not the owner. Please use 'Create New Shuffled' instead."}
                
            new_pid = pid
            user_client.playlist_replace_items(new_pid, shuffled_uris[:100])
            for i in range(100, len(shuffled_uris), 100):
                user_client.playlist_add_items(new_pid, shuffled_uris[i:i+100])
            msg = f"Successfully shuffled {total_songs} songs in-place!"
        else:
            final_name = payload.new_name.strip() if payload.new_name and payload.new_name.strip() else original_name
            new_playlist = user_client.current_user_playlist_create(
                name=final_name,
                public=playlist.get("public", False),
                description=f"Shuffled version of {original_name}"
            )
            new_pid = new_playlist["id"]
            user_client.playlist_add_items(new_pid, shuffled_uris[:100])
            for i in range(100, len(shuffled_uris), 100):
                user_client.playlist_add_items(new_pid, shuffled_uris[i:i+100])
            msg = f"Successfully mixed and shuffled {total_songs} songs into '{final_name}'!"

        formatted_songs = []
        for t in shuffled:
            artists = ", ".join(a.get("name", "Unknown") for a in t.get("artists", []))
            album_imgs = t.get("album", {}).get("images") or []
            cover = album_imgs[0].get("url") if album_imgs else None
            formatted_songs.append({
                "name": t.get("name"),
                "artist": artists,
                "uri": t.get("uri"),
                "duration_ms": t.get("duration_ms", 0),
                "popularity": t.get("popularity", 50),
                "album_name": t.get("album", {}).get("name", ""),
                "album_cover": cover,
                "spotify_url": t.get("external_urls", {}).get("spotify")
            })

        return {
            "success": True,
            "playlist_id": new_pid,
            "song_count": total_songs,
            "message": msg,
            "tracks": formatted_songs
        }
    except Exception as e:
        return {"success": False, "error": str(e)}



class PlaylistDedupeRequest(BaseModel):
    playlist_id: str

@app.post("/api/playlist/dedupe")
def dedupe_playlist(payload: PlaylistDedupeRequest):
    """Removes duplicate songs (same name and artist) from a playlist in-place."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required. Click 'Connect Spotify' in the top right to link your account."
        }

    try:
        pid = payload.playlist_id.strip()
        if "playlist/" in pid:
            pid = pid.split("playlist/")[1]
        elif "spotify:playlist:" in pid:
            pid = pid.split("spotify:playlist:")[1]
        pid = pid.split("?")[0].split("/")[0]

        pl = user_client.playlist(pid, fields="snapshot_id")
        snapshot_id = pl.get("snapshot_id")

        items = []
        res = user_client.playlist_items(pid, limit=100)
        while res:
            items.extend(res.get("items", []))
            if res.get("next"):
                res = user_client.next(res)
            else:
                break

        seen = set()
        removals = []

        for idx, it in enumerate(items):
            t = it.get("track") or it.get("item")
            if not t or not t.get("uri"):
                continue
                
            uri = t.get("uri")
            name = t.get("name", "").strip().lower()
            artists = ", ".join(a.get("name", "").strip().lower() for a in t.get("artists", []))
            
            key = f"{name}::{artists}"
            
            if key in seen:
                removals.append((idx, uri))
            else:
                seen.add(key)
                
        if not removals:
            return {"success": True, "removed_count": 0, "message": "No duplicates found! Your playlist is clean."}
            
        removals.sort(key=lambda x: x[0], reverse=True)
        remove_payload = [{"uri": uri, "positions": [idx]} for idx, uri in removals]
            
        # Process in batches of 100
        for i in range(0, len(remove_payload), 100):
            batch = remove_payload[i:i+100]
            del_res = user_client.playlist_remove_specific_occurrences_of_items(pid, batch, snapshot_id)
            if del_res and "snapshot_id" in del_res:
                snapshot_id = del_res["snapshot_id"]
                
        # Update our local live cache
        original_total = len(items)
        recently_modified_counts[pid] = original_total - len(removals)
            
        return {"success": True, "removed_count": len(removals), "message": f"Successfully removed {len(removals)} duplicate song(s)."}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


class PlaylistCombineRequest(BaseModel):
    playlist_ids: List[str]
    new_name: str

@app.post("/api/playlist/combine")
def combine_playlists(payload: PlaylistCombineRequest):
    """Combines multiple playlists into a single new playlist."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {"success": False, "error": "Spotify authorization required."}
        
    try:
        if not payload.playlist_ids:
            return {"success": False, "error": "No playlists selected."}
            
        all_uris = []
        for pid in payload.playlist_ids:
            pid = pid.strip()
            if "playlist/" in pid:
                pid = pid.split("playlist/")[1]
            elif "spotify:playlist:" in pid:
                pid = pid.split("spotify:playlist:")[1]
            pid = pid.split("?")[0].split("/")[0]
            
            items = []
            try:
                res = user_client.playlist_items(pid, limit=100)
                while res:
                    items.extend(res.get("items", []))
                    if res.get("next"):
                        res = user_client.next(res)
                    else:
                        break
            except Exception as e:
                if "403" in str(e):
                    try:
                        from spotipy.oauth2 import SpotifyClientCredentials
                        client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
                        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
                        app_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                        res = app_client.playlist_items(pid, limit=100)
                        while res:
                            items.extend(res.get("items", []))
                            if res.get("next"):
                                res = app_client.next(res)
                            else:
                                break
                    except Exception as app_e:
                        return {"success": False, "error": f"Spotify refused access to one of the playlists (403 Forbidden)."}
                else:
                    raise e
                    
            for it in items:
                t = it.get("track") or it.get("item")
                if t and t.get("uri") and t.get("uri").startswith("spotify:track:"):
                    all_uris.append(t.get("uri"))
                    
        if not all_uris:
            return {"success": False, "error": "No valid tracks found to combine."}
            
        new_playlist = user_client.current_user_playlist_create(
            name=payload.new_name or "Combined Playlist",
            public=False,
            description="Combined playlist from multiple sources."
        )
        new_pid = new_playlist["id"]
        
        for i in range(0, len(all_uris), 100):
            user_client.playlist_add_items(new_pid, all_uris[i:i+100])
            
        recently_modified_counts[new_pid] = len(all_uris)
        
        return {
            "success": True,
            "playlist_id": new_pid,
            "song_count": len(all_uris),
            "message": f"Successfully combined {len(payload.playlist_ids)} playlists into '{payload.new_name}' with {len(all_uris)} songs!"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class QueueRequest(BaseModel):
    track_uris: List[str]


@app.post("/api/player/queue")
def queue_tracks(payload: QueueRequest):
    """Sends tracks in the Send Box directly to the active Spotify playback queue."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required. Click 'Connect Spotify' in the top right to link your account."
        }

    try:
        valid_uris = [u for u in payload.track_uris if u and u.startswith("spotify:track:")]
        queued = 0
        errors = []
        for uri in valid_uris:
            try:
                user_client.add_to_queue(uri=uri)
                queued += 1
            except Exception as q_err:
                errors.append(str(q_err))

        return {
            "success": queued > 0,
            "queued": queued,
            "total": len(valid_uris),
            "errors": errors[:2]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class PlayRequest(BaseModel):
    track_uri: str

@app.post("/api/player/play")
def play_track(payload: PlayRequest):
    """Plays a specific track instantly on the active device."""
    user_client = _get_valid_user_client()
    if not user_client:
        return {
            "success": False,
            "need_auth": True,
            "auth_url": oauth_manager.get_authorize_url(),
            "error": "Spotify authorization required to control playback."
        }
    try:
        user_client.start_playback(uris=[payload.track_uri])
        return {"success": True}
    except spotipy.exceptions.SpotifyException as e:
        # Code 403 often means no active device or premium required
        return {"success": False, "error": "Could not play track. Make sure Spotify is open and active on one of your devices."}
    except Exception as e:
        return {"success": False, "error": str(e)}



@app.get("/tools", response_class=HTMLResponse)
def serve_tools():
    """Serves the new tools (shuffle, dedupe, combine) frontend page."""
    template_path = BASE_DIR / "templates" / "tools.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    template_path = BASE_DIR / "templates" / "index.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import threading
    import time
    import webbrowser
    import uvicorn

    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://127.0.0.1:8000")

    threading.Thread(target=open_browser, daemon=True).start()
    print("\n" + "=" * 55)
    print(" Soundtrack Curator Studio is RUNNING!")
    print(" Open your browser at: http://127.0.0.1:8000")
    print(" Press CTRL+C to stop the server.")
    print("=" * 55 + "\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
