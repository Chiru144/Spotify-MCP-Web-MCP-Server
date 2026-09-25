import os
import re
import threading
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Prevent local mcp.py from shadowing the installed 'mcp' package
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir in sys.path:
    sys.path.remove(current_dir)
if '' in sys.path:
    sys.path.remove('')

from mcp.server.mcpserver import MCPServer as FastMCP
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Import DuckDuckGo Search (support both ddgs and duckduckgo_search packages)
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# Load environment variables from .env file located alongside server.py
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize FastMCP server
mcp = FastMCP("Spotify Actor Filmography MCP")

# Define Spotify Scopes needed for playlist creation and playback control
SPOTIFY_SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-read-private",
    "user-read-email",
]

TMDB_BASE_URL = "https://api.themoviedb.org/3"


def get_spotify_client() -> spotipy.Spotify:
    """Initialize and return an authenticated Spotipy client."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI") or os.getenv("SPOTIFY_REDIRECT_URI") or "http://127.0.0.1:8888/callback"

    if not client_id or "your_spotify_client_id" in client_id:
        raise ValueError("Missing SPOTIPY_CLIENT_ID in .env. Please configure your Spotify credentials.")
    if not client_secret or "your_spotify_client_secret" in client_secret:
        raise ValueError("Missing SPOTIPY_CLIENT_SECRET in .env. Please configure your Spotify credentials.")

    cache_path = str(Path(__file__).parent / ".spotipyoauthcache")

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SPOTIFY_SCOPES),
        cache_path=cache_path,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


# =====================================================================
# TMDB (The Movie Database) API Client & Helpers
# =====================================================================

def tmdb_get_auth_headers() -> Dict[str, str]:
    """Return authorization headers for TMDB API."""
    token = os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN")
    headers = {"accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def tmdb_get_auth_params() -> Dict[str, str]:
    """Return query params if API key is used as fallback."""
    token = os.getenv("TMDB_READ_ACCESS_TOKEN") or os.getenv("TMDB_ACCESS_TOKEN")
    api_key = os.getenv("TMDB_API_KEY")
    params: Dict[str, str] = {}
    if not token and api_key:
        params["api_key"] = api_key
    return params


def tmdb_search_person(actor_name: str) -> Optional[Dict[str, Any]]:
    """Search TMDB for a person by name and return top matching person details."""
    headers = tmdb_get_auth_headers()
    params = tmdb_get_auth_params()
    
    import re
    clean_name = actor_name.lower()
    for word in ["kannada", "telugu", "tamil", "hindi", "malayalam", "english", "bollywood", "tollywood", "kollywood", "sandalwood", "actor", "actress", "singer", "director"]:
        clean_name = re.sub(rf"\b{word}\b", "", clean_name)
    clean_name = clean_name.strip() or actor_name

    params.update({"query": clean_name, "include_adult": "false", "language": "en-US", "page": "1"})

    try:
        resp = requests.get(f"{TMDB_BASE_URL}/search/person", headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                # Prioritize acting department if available
                acting_matches = [r for r in results if r.get("known_for_department") == "Acting"]
                return acting_matches[0] if acting_matches else results[0]
    except Exception:
        pass
    return None


def tmdb_get_actor_movie_credits(person_id: int, sort_by: str = "popularity") -> List[Dict[str, Any]]:
    """Fetch movie credits for an actor from TMDB.
    
    Args:
        person_id: TMDB person ID
        sort_by: 'popularity' or 'release_date'
    """
    headers = tmdb_get_auth_headers()
    params = tmdb_get_auth_params()
    params.update({"language": "en-US"})

    try:
        resp = requests.get(f"{TMDB_BASE_URL}/person/{person_id}/movie_credits", headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            cast_entries = data.get("cast", [])

            # Filter valid movie titles and deduplicate
            unique_movies: Dict[int, Dict[str, Any]] = {}
            for entry in cast_entries:
                movie_id = entry.get("id")
                title = entry.get("title") or entry.get("original_title")
                if movie_id and title and movie_id not in unique_movies:
                    unique_movies[movie_id] = {
                        "id": movie_id,
                        "title": title,
                        "character": entry.get("character", ""),
                        "release_date": entry.get("release_date", ""),
                        "popularity": entry.get("popularity", 0.0),
                        "vote_average": entry.get("vote_average", 0.0),
                        "vote_count": entry.get("vote_count", 0),
                        "overview": entry.get("overview", "")
                    }

            movie_list = list(unique_movies.values())
            if sort_by == "release_date":
                movie_list.sort(key=lambda m: m["release_date"] or "0000", reverse=True)
            else:
                movie_list.sort(key=lambda m: m["popularity"] or 0.0, reverse=True)

            return movie_list
    except Exception:
        pass
    return []


def tmdb_search_movie_details(movie_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search TMDB for movies matching a name."""
    headers = tmdb_get_auth_headers()
    params = tmdb_get_auth_params()
    params.update({"query": movie_name, "include_adult": "false", "language": "en-US", "page": "1"})

    try:
        resp = requests.get(f"{TMDB_BASE_URL}/search/movie", headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            return results[:limit]
    except Exception:
        pass
    return []


def tmdb_get_person_profile(person_id: int) -> Optional[Dict[str, Any]]:
    """Get full biographical details for a person from TMDB."""
    headers = tmdb_get_auth_headers()
    params = tmdb_get_auth_params()
    params.update({"language": "en-US"})

    try:
        resp = requests.get(f"{TMDB_BASE_URL}/person/{person_id}", headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# =====================================================================
# DuckDuckGo Search Helpers
# =====================================================================

def ddg_web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Execute a web search using DuckDuckGo and return list of result items."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", "")
                }
                for r in results
            ]
    except Exception:
        return []


def ddg_find_soundtrack_songs(movie_name: str, max_songs: int = 5) -> List[str]:
    """Search DuckDuckGo to extract known soundtrack song titles for a movie.
    
    Helps discover regional or non-standard soundtrack track names to search on Spotify.
    """
    song_titles: List[str] = []
    queries = [
        f'"{movie_name}" soundtrack tracklist songs',
        f'"{movie_name}" movie songs list',
    ]

    for q in queries:
        results = ddg_web_search(q, max_results=3)
        for item in results:
            text = f"{item['title']} {item['body']}"
            # Match quotes or track listings e.g. "Song Name", 1. Song Name
            quoted = re.findall(r'["“]([^"”]{3,40})["”]', text)
            for s in quoted:
                clean = s.strip()
                if (
                    clean
                    and clean.lower() not in [movie_name.lower(), "soundtrack", "ost", "theme", "original soundtrack"]
                    and not clean.lower().startswith("http")
                ):
                    if clean not in song_titles:
                        song_titles.append(clean)

            # Match numbered lines e.g. "1. Song Name" or "1 - Song Name"
            numbered = re.findall(r'(?:^|\n|\. )\d+[\.\-]\s*([A-Za-z0-9\s\',-]{3,40})', text)
            for s in numbered:
                clean = s.strip()
                if clean and clean not in song_titles and len(clean) > 3:
                    song_titles.append(clean)

            if len(song_titles) >= max_songs:
                break
        if len(song_titles) >= max_songs:
            break

    return song_titles[:max_songs]


# =====================================================================
# Wikipedia Web Scraper (Fallback Discovery)
# =====================================================================

def scrape_actor_movies_from_web(actor_name: str) -> List[str]:
    """Search Wikipedia to extract the filmography for an actor as a tertiary fallback."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    urls = []
    queries = [
        f"{actor_name} filmography",
        actor_name
    ]

    for q in queries:
        try:
            encoded_query = urllib.parse.quote(q)
            api_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded_query}&limit=5&format=json"
            resp = s.get(api_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 3 and data[3]:
                    for u in data[3]:
                        if "filmography" in u.lower():
                            urls.insert(0, u)
                        else:
                            urls.append(u)
                    if urls:
                        break
        except Exception:
            continue

    if not urls:
        return []

    movies: List[str] = []
    excluded_keywords = {
        "title", "film", "role", "notes", "year", "director", "ref", "awards",
        "work", "character", "episodes", "episode", "season", "soundtrack", "album"
    }

    for target_url in urls[:2]:
        try:
            page_resp = s.get(target_url, timeout=10)
            if page_resp.status_code != 200:
                continue
            soup = BeautifulSoup(page_resp.text, "html.parser")

            for table in soup.find_all("table", class_="wikitable"):
                for row in table.find_all("tr"):
                    for i_tag in row.find_all("i"):
                        text = i_tag.get_text().strip()
                        if text and len(text) > 1 and not text.isdigit():
                            if text.lower() not in excluded_keywords:
                                movies.append(text)
            if movies:
                break
        except Exception:
            continue

    seen = set()
    unique_movies: List[str] = []
    for m in movies:
        norm = m.lower()
        if norm not in seen:
            seen.add(norm)
            unique_movies.append(m)

    return unique_movies


# =====================================================================
# Multi-Source Filmography Resolver
# =====================================================================

def get_actor_filmography(actor_name: str, limit: int = 30, sort_by: str = "popularity") -> Dict[str, Any]:
    """Retrieve an actor's filmography using a multi-tiered strategy:
    1. TMDB (Primary - high accuracy, characters, release dates)
    2. DuckDuckGo Search (Secondary - handles regional / unindexed names)
    3. Wikipedia Scraper (Tertiary)
    """
    # Tier 1: TMDB
    tmdb_person = tmdb_search_person(actor_name)
    if tmdb_person:
        person_id = tmdb_person["id"]
        credits = tmdb_get_actor_movie_credits(person_id, sort_by=sort_by)
        if credits:
            return {
                "source": "TMDB",
                "actor_name": tmdb_person.get("name", actor_name),
                "person_id": person_id,
                "profile_path": tmdb_person.get("profile_path", ""),
                "popularity": tmdb_person.get("popularity", 0.0),
                "movies": credits[:limit]
            }

    # Tier 2: Wikipedia Scraper
    wiki_movies = scrape_actor_movies_from_web(actor_name)
    if wiki_movies:
        return {
            "source": "Wikipedia",
            "actor_name": actor_name,
            "person_id": None,
            "profile_path": "",
            "popularity": 0.0,
            "movies": [{"title": m, "release_date": "", "character": ""} for m in wiki_movies[:limit]]
        }

    # Tier 3: DuckDuckGo Search
    ddg_results = ddg_web_search(f"{actor_name} filmography movies list", max_results=5)
    extracted: List[str] = []
    for r in ddg_results:
        snippets = f"{r['title']} {r['body']}"
        quoted = re.findall(r'["“]([^"”]{3,40})["”]', snippets)
        for q in quoted:
            if q.lower() not in extracted and q.lower() not in [actor_name.lower(), "filmography"]:
                extracted.append(q)

    if extracted:
        return {
            "source": "DuckDuckGo",
            "actor_name": actor_name,
            "person_id": None,
            "profile_path": "",
            "popularity": 0.0,
            "movies": [{"title": m, "release_date": "", "character": ""} for m in extracted[:limit]]
        }

    return {
        "source": "None",
        "actor_name": actor_name,
        "person_id": None,
        "profile_path": "",
        "popularity": 0.0,
        "movies": []
    }


# =====================================================================
# Intelligent Spotify Soundtrack Track Matcher
# =====================================================================
def fetch_tracks_for_movie(sp: spotipy.Spotify, movie_name: str, max_songs: int = 5) -> List[Dict[str, str]]:
    """Search Spotify for soundtrack albums and songs from a movie.
    
    Uses a 3-tier matching engine:
    1. Spotify Soundtrack Album search
    2. Spotify Track search
    3. DuckDuckGo tracklist discovery + Spotify direct search
    """
    tracks: List[Dict[str, str]] = []
    seen_uris = set()

    # Strategy 1: Search for movie soundtrack/album
    album_queries = [
        f'album:"{movie_name}"',
        f"{movie_name} soundtrack",
        f"{movie_name} original motion picture soundtrack",
        movie_name
    ]

    for query in album_queries:
        try:
            album_results = sp.search(q=query, type="album", limit=3)
            albums = album_results.get("albums", {}).get("items", [])
            for album in albums:
                if is_fuzzy_match(movie_name, album.get("name", "")):
                    album_tracks = sp.album_tracks(album["id"], limit=max_songs)
                    for item in album_tracks.get("items", []):
                        uri = item.get("uri")
                        if uri and uri not in seen_uris:
                            seen_uris.add(uri)
                            artists = ", ".join(a["name"] for a in item.get("artists", []))
                            artist_ids = [a["id"] for a in item.get("artists", []) if "id" in a]
                            tracks.append({
                                "title": item.get("name", "Unknown"),
                                "artists": artists,
                                "artist_ids": artist_ids,
                                "uri": uri,
                                "movie": movie_name,
                                "album": album.get("name", "")
                            })
                            if len(tracks) >= max_songs:
                                return tracks
        except Exception:
            pass

    # Strategy 2: Search tracks directly on Spotify
    track_queries = [
        f'track:"{movie_name}"',
        f"{movie_name} song",
        f"{movie_name} theme",
        movie_name
    ]
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

    for tq in track_queries:
        if len(tracks) >= max_songs:
            break
        try:
            results = sp.search(q=tq, type="track", limit=max_songs)
            items = results.get("tracks", {}).get("items", [])
            for item in items:
                uri = item.get("uri")
                track_name = item.get("name", "").lower()
                album_name = item.get("album", {}).get("name", "").lower()
                
                # Stricter matching: require the movie name to be in the track or album name (with fuzzy match)
                if not is_fuzzy_match(movie_name, track_name) and not is_fuzzy_match(movie_name, album_name):
                    continue
                    
                if uri and uri not in seen_uris:
                    seen_uris.add(uri)
                    artists = ", ".join(a["name"] for a in item.get("artists", []))
                    artist_ids = [a["id"] for a in item.get("artists", []) if "id" in a]
                    tracks.append({
                        "title": item.get("name", "Unknown"),
                        "artists": artists,
                        "artist_ids": artist_ids,
                        "uri": uri,
                        "movie": movie_name,
                        "album": item.get("album", {}).get("name", "")
                    })
                    if len(tracks) >= max_songs:
                        break
        except Exception:
            pass

    # Strategy 3: DuckDuckGo-assisted song title resolution
    if len(tracks) < 2:
        try:
            ddg_song_names = ddg_find_soundtrack_songs(movie_name, max_songs=max_songs)
            for song_title in ddg_song_names:
                if len(tracks) >= max_songs:
                    break
                # Search Spotify for the specific song name discovered via DDG
                res = sp.search(q=f"{song_title} {movie_name}", type="track", limit=1)
                items = res.get("tracks", {}).get("items", [])
                if not items:
                    res = sp.search(q=song_title, type="track", limit=1)
                    items = res.get("tracks", {}).get("items", [])
                if items:
                    t = items[0]
                    uri = t.get("uri")
                    track_name = t.get("name", "").lower()
                    album_name = t.get("album", {}).get("name", "").lower()
                    
                    # Stricter matching: require the movie name to be in the track or album name
                    if not is_fuzzy_match(movie_name, track_name) and not is_fuzzy_match(movie_name, album_name):
                        continue
                        
                    if uri and uri not in seen_uris:
                        seen_uris.add(uri)
                        artists = ", ".join(a["name"] for a in t.get("artists", []))
                        artist_ids = [a["id"] for a in t.get("artists", []) if "id" in a]
                        tracks.append({
                            "title": t.get("name", song_title),
                            "artists": artists,
                            "artist_ids": artist_ids,
                            "uri": uri,
                            "movie": movie_name,
                            "album": t.get("album", {}).get("name", "")
                        })
        except Exception:
            pass

    return tracks


# =====================================================================
# Actor, Movie & Search FastMCP Tools
# =====================================================================

@mcp.tool()
def search_actor_movies(actor_name: str, limit: int = 30, sort_by: str = "popularity") -> str:
    """Discover the full filmography for an actor using TMDB (with DDG and Wikipedia fallbacks).
    
    Args:
        actor_name: Name of the actor (e.g. 'Cillian Murphy', 'Shah Rukh Khan', 'Tom Cruise')
        limit: Maximum number of movies to return (default: 30)
        sort_by: Ordering for movies ('popularity' or 'release_date', default: 'popularity')
    """
    try:
        data = get_actor_filmography(actor_name, limit=limit, sort_by=sort_by)
        movies = data.get("movies", [])
        source = data.get("source", "Unknown")

        if not movies:
            return f"No movies found for actor '{actor_name}' across TMDB, DuckDuckGo, and Wikipedia."

        lines = [
            f"Filmography for {data.get('actor_name', actor_name)} (Source: {source}):",
            f"Total found: {len(movies)} (sorted by {sort_by})"
        ]

        for idx, m in enumerate(movies, 1):
            title = m.get("title", "Unknown")
            year = m.get("release_date", "")[:4] if m.get("release_date") else ""
            char = m.get("character")
            year_str = f" ({year})" if year else ""
            char_str = f" - Role: '{char}'" if char else ""
            rating_str = f" [Rating: {m.get('vote_average')}/10]" if m.get("vote_average") else ""
            lines.append(f"{idx}. {title}{year_str}{char_str}{rating_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching movies for {actor_name}: {str(e)}"


@mcp.tool()
def get_actor_tmdb_profile(actor_name: str) -> str:
    """Get rich biographical and career profile details for an actor from TMDB.
    
    Args:
        actor_name: Name of the actor (e.g. 'Robert Downey Jr.', 'Zendaya')
    """
    try:
        person = tmdb_search_person(actor_name)
        if not person:
            return f"Actor '{actor_name}' not found on TMDB."

        person_id = person["id"]
        profile = tmdb_get_person_profile(person_id) or person
        credits = tmdb_get_actor_movie_credits(person_id, sort_by="popularity")

        bio = profile.get("biography", "").strip()
        if len(bio) > 400:
            bio = bio[:400] + "..."

        top_movies = [c["title"] for c in credits[:5]]

        lines = [
            f"TMDB Profile: {profile.get('name', actor_name)}",
            f"Known For: {profile.get('known_for_department', 'Acting')}",
            f"Birthday: {profile.get('birthday', 'N/A')}",
            f"Place of Birth: {profile.get('place_of_birth', 'N/A')}",
            f"TMDB Popularity Score: {profile.get('popularity', 'N/A')}",
            f"TMDB ID: {person_id}",
            f"\nTop Known Movies: {', '.join(top_movies) if top_movies else 'N/A'}",
            f"\nBiography:\n{bio if bio else 'No biography available.'}"
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving TMDB profile for {actor_name}: {str(e)}"


@mcp.tool()
def search_movie_tmdb(movie_name: str, limit: int = 5) -> str:
    """Search TMDB for movie information, release year, ratings, and overview.
    
    Args:
        movie_name: Title of the movie to search (e.g. 'Inception', 'Interstellar')
        limit: Maximum results to return (default: 5)
    """
    try:
        results = tmdb_search_movie_details(movie_name, limit=limit)
        if not results:
            return f"No movie matching '{movie_name}' found on TMDB."

        lines = [f"TMDB Movies found for '{movie_name}':"]
        for idx, m in enumerate(results, 1):
            title = m.get("title", "Unknown")
            year = m.get("release_date", "")[:4] or "N/A"
            rating = m.get("vote_average", "N/A")
            votes = m.get("vote_count", 0)
            overview = m.get("overview", "")
            if len(overview) > 150:
                overview = overview[:150] + "..."
            lines.append(f"\n{idx}. {title} ({year}) - Rating: {rating}/10 ({votes:,} votes) [ID: {m.get('id')}]")
            if overview:
                lines.append(f"   Overview: {overview}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching TMDB for movie '{movie_name}': {str(e)}"


@mcp.tool()
def search_duckduckgo(query: str, max_results: int = 5) -> str:
    """Perform a web search using DuckDuckGo to look up movie news, filmographies, or sound tracks.
    
    Args:
        query: Search query string
        max_results: Maximum results to return (default: 5)
    """
    try:
        results = ddg_web_search(query, max_results=max_results)
        if not results:
            return f"No DuckDuckGo results found for '{query}'."

        lines = [f"DuckDuckGo search results for '{query}':"]
        for idx, r in enumerate(results, 1):
            lines.append(f"\n{idx}. {r['title']}")
            lines.append(f"   Link: {r['href']}")
            lines.append(f"   Snippet: {r['body']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching DuckDuckGo: {str(e)}"


@mcp.tool()
def get_movie_songs(movie_name: str, limit: int = 10) -> str:
    """Search Spotify for soundtrack albums and songs from a movie with DuckDuckGo fallback assistance.
    
    Args:
        movie_name: Title of the movie (e.g. 'Inception', 'Darr', 'Top Gun')
        limit: Maximum number of songs to return (default: 10)
    """
    try:
        sp = get_spotify_client()
        tracks = fetch_tracks_for_movie(sp, movie_name, max_songs=limit)
        if not tracks:
            return f"No songs found on Spotify for movie '{movie_name}'."

        lines = [f"Songs found for '{movie_name}':"]
        for idx, t in enumerate(tracks, 1):
            album_info = f" [Album: {t['album']}]" if t['album'] else ""
            lines.append(f"{idx}. {t['title']} - {t['artists']}{album_info} (URI: {t['uri']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving songs for movie '{movie_name}': {str(e)}"


@mcp.tool()
def create_actor_playlist(
    actor_name: str,
    playlist_name: Optional[str] = None,
    max_movies: int = 10,
    max_songs_per_movie: int = 3,
    specific_movies: Optional[str] = None,
    sort_by: str = "popularity",
    public: bool = True
) -> str:
    """End-to-End Pipeline: Discover an actor's filmography via TMDB/DDG, locate songs on Spotify,
    create a new playlist, and add all tracks.
    
    Args:
        actor_name: Name of the actor (e.g., 'Cillian Murphy', 'Shah Rukh Khan', 'Keanu Reeves')
        playlist_name: Optional custom name for the playlist
        max_movies: Number of movies to pull songs from (default: 10)
        max_songs_per_movie: Number of songs to add per movie (default: 3)
        specific_movies: Optional comma-separated list of specific movies to use (e.g. 'Inception, Dunkirk, Oppenheimer')
        sort_by: Filmography sort order ('popularity' or 'release_date', default: 'popularity')
        public: Whether the created playlist is public (default: True)
    """
    try:
        sp = get_spotify_client()
        user_info = sp.current_user()
        user_id = user_info["id"]

        # Step 1: Discover movies
        source_note = ""
        if specific_movies:
            movie_list = [m.strip() for m in specific_movies.split(",") if m.strip()]
            source_note = "User-specified list"
        else:
            film_data = get_actor_filmography(actor_name, limit=max_movies, sort_by=sort_by)
            source_note = f"Discovered via {film_data.get('source', 'Web')}"
            movies = film_data.get("movies", [])
            if not movies:
                return f"Could not find any movies online for actor '{actor_name}'."
            movie_list = [m["title"] for m in movies[:max_movies]]

        # Step 2: Fetch tracks for each movie
        all_tracks: List[Dict[str, str]] = []
        track_breakdown: List[str] = []

        for movie in movie_list:
            m_tracks = fetch_tracks_for_movie(sp, movie, max_songs=max_songs_per_movie)
            if m_tracks:
                all_tracks.extend(m_tracks)
                song_titles = ", ".join(f"'{t['title']}'" for t in m_tracks)
                track_breakdown.append(f"• {movie}: {len(m_tracks)} song(s) ({song_titles})")
            else:
                track_breakdown.append(f"• {movie}: (no tracks found on Spotify)")

        if not all_tracks:
            return f"Found movies for '{actor_name}', but could not locate matching songs on Spotify."

        # Step 3: Create the Spotify playlist
        p_name = playlist_name or f"{actor_name} - Filmography Soundtracks"
        description = f"Curated filmography soundtracks for {actor_name}. Generated via TMDB, DuckDuckGo & Spotify MCP."
        playlist = sp.current_user_playlist_create(
            name=p_name,
            public=public,
            description=description
        )
        playlist_id = playlist["id"]
        playlist_url = playlist.get("external_urls", {}).get("spotify", "")

        # Step 4: Batch add tracks (Spotify allows max 100 per call)
        track_uris = [t["uri"] for t in all_tracks]
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i + 100]
            sp.playlist_add_items(playlist_id=playlist_id, items=batch)

        result_lines = [
            f"Successfully created playlist '{p_name}' for {actor_name}!",
            f"Playlist Link: {playlist_url}",
            f"Playlist ID: {playlist_id}",
            f"Source: {source_note}",
            f"Total Songs Added: {len(all_tracks)} across {len(movie_list)} movies.",
            "\nBreakdown by movie:",
            *track_breakdown
        ]
        return "\n".join(result_lines)

    except Exception as e:
        return f"Error creating actor playlist: {str(e)}"


# =====================================================================
# Spotify Playlist & Playback Management Tools
# =====================================================================

@mcp.tool()
def create_playlist(name: str, description: str = "", public: bool = True) -> str:
    """Create a new Spotify playlist for the user.
    
    Args:
        name: Name of the playlist
        description: Description of the playlist
        public: Whether the playlist is public (default: True)
    """
    try:
        sp = get_spotify_client()
        playlist = sp.current_user_playlist_create(
            name=name,
            public=public,
            description=description
        )
        url = playlist.get("external_urls", {}).get("spotify", "")
        return f"Playlist '{name}' created successfully!\nID: {playlist['id']}\nURL: {url}"
    except Exception as e:
        return f"Error creating playlist: {str(e)}"


@mcp.tool()
def shuffle_playlist(playlist_id: str) -> str:
    """Mix and shuffle all songs in a Spotify playlist into a completely new random order.
    
    Args:
        playlist_id: The Spotify ID, URI, or URL of the playlist to shuffle
    """
    try:
        import random
        sp = get_spotify_client()
        pid = playlist_id.split(":")[-1].split("/")[-1].split("?")[0]
        
        # Fetch all songs from the playlist
        items = []
        res = sp.playlist_items(pid, limit=100)
        while res:
            items.extend(res.get("items", []))
            if res.get("next"):
                res = sp.next(res)
            else:
                break
                
        valid_tracks = [it["track"] for it in items if it.get("track") and it["track"].get("uri")]
        if not valid_tracks:
            return f"No songs found in playlist {pid} to shuffle."
            
        total_songs = len(valid_tracks)
        shuffled = list(valid_tracks)
        random.shuffle(shuffled)
        
        shuffled_uris = [t["uri"] for t in shuffled if t.get("uri", "").startswith("spotify:track:")]
        if shuffled_uris:
            sp.playlist_replace_items(pid, shuffled_uris[:100])
            for i in range(100, len(shuffled_uris), 100):
                sp.playlist_add_items(pid, shuffled_uris[i:i+100])
                
        preview_lines = [f"{idx}. {t['name']} - {', '.join(a['name'] for a in t.get('artists', []))}" for idx, t in enumerate(shuffled[:5], 1)]
        preview_text = "\n".join(preview_lines)
        more_text = f"\n... and {total_songs - 5} more songs" if total_songs > 5 else ""
        
        return f"Successfully mixed and shuffled all {total_songs} songs in playlist {pid} in a new random order!\n\nNew song order preview (first {min(5, total_songs)} of {total_songs} songs):\n{preview_text}{more_text}"
    except Exception as e:
        return f"Error shuffling playlist: {str(e)}"


@mcp.tool()
def add_tracks_to_playlist(playlist_id: str, track_uris: List[str]) -> str:
    """Add a list of Spotify song URIs to an existing playlist.
    
    Args:
        playlist_id: The Spotify ID or URI of the playlist
        track_uris: List of Spotify song URIs (e.g. ['spotify:track:...', ...])
    """
    try:
        sp = get_spotify_client()
        pid = playlist_id.split(":")[-1].split("/")[-1].split("?")[0]
        total_added = 0
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i + 100]
            sp.playlist_add_items(playlist_id=pid, items=batch)
            total_added += len(batch)
        return f"Successfully added {total_added} song(s) to playlist {pid}."
    except Exception as e:
        return f"Error adding songs to playlist: {str(e)}"

@mcp.tool()
def combine_playlists(playlist_ids: List[str], new_name: str = "Combined Playlist", description: str = "Combined playlist from multiple sources.") -> str:
    """Combines multiple Spotify playlists into a single new playlist.
    
    Args:
        playlist_ids: A list of Spotify playlist IDs, URIs, or URLs to combine.
        new_name: The name for the newly created combined playlist.
        description: The description for the new playlist.
    """
    try:
        sp = get_spotify_client()
        user_id = sp.me()["id"]
        
        all_uris = []
        for playlist_url in playlist_ids:
            pid = playlist_url.split(":")[-1].split("/")[-1].split("?")[0]
            items = []
            res = sp.playlist_items(pid, limit=100)
            while res:
                items.extend(res.get("items", []))
                if res.get("next"):
                    res = sp.next(res)
                else:
                    break
            uris = [it["track"]["uri"] for it in items if it.get("track") and it["track"].get("uri") and it["track"]["uri"].startswith("spotify:track:")]
            all_uris.extend(uris)
            
        if not all_uris:
            return "No valid songs found in the provided playlists to combine."
            
        # Deduplicate
        seen = set()
        deduped_uris = [uri for uri in all_uris if not (uri in seen or seen.add(uri))]
        
        new_playlist = sp.user_playlist_create(
            user=user_id,
            name=new_name,
            public=False,
            description=description
        )
        new_pid = new_playlist["id"]
        
        for i in range(0, len(deduped_uris), 100):
            sp.playlist_add_items(new_pid, deduped_uris[i:i+100])
            
        return f"Successfully combined {len(playlist_ids)} playlists into '{new_name}' with {len(deduped_uris)} unique songs! New Playlist ID: {new_pid}"
    except Exception as e:
        return f"Error combining playlists: {str(e)}"

@mcp.tool()
def dedupe_playlist(playlist_id: str) -> str:
    """Removes all duplicate songs from a Spotify playlist, keeping only the first occurrence of each song.
    
    Args:
        playlist_id: The Spotify ID, URI, or URL of the playlist to deduplicate.
    """
    try:
        sp = get_spotify_client()
        pid = playlist_id.split(":")[-1].split("/")[-1].split("?")[0]
        
        # Fetch all songs
        items = []
        res = sp.playlist_items(pid, limit=100)
        while res:
            items.extend(res.get("items", []))
            if res.get("next"):
                res = sp.next(res)
            else:
                break
                
        valid_items = [it for it in items if it.get("track") and it["track"].get("uri")]
        if not valid_items:
            return f"No songs found in playlist {pid}."
            
        seen_uris = set()
        deduped_uris = []
        duplicates = 0
        
        for it in valid_items:
            uri = it["track"]["uri"]
            if not uri.startswith("spotify:track:"): continue
            
            if uri in seen_uris:
                duplicates += 1
            else:
                seen_uris.add(uri)
                deduped_uris.append(uri)
                
        if duplicates == 0:
            return f"Playlist {pid} has no duplicate songs. It is already clean!"
            
        # Replace the entire playlist with the deduped list
        if deduped_uris:
            sp.playlist_replace_items(pid, deduped_uris[:100])
            for i in range(100, len(deduped_uris), 100):
                sp.playlist_add_items(pid, deduped_uris[i:i+100])
        else:
            sp.playlist_replace_items(pid, [])
            
        return f"Successfully removed {duplicates} duplicate songs from playlist {pid}! The playlist now has {len(deduped_uris)} unique songs."
    except Exception as e:
        return f"Error deduplicating playlist: {str(e)}"


@mcp.tool()
def add_songs_to_playlist(playlist_id: str, song_uris: List[str]) -> str:
    """Add a list of Spotify song URIs to an existing playlist.
    
    Args:
        playlist_id: The Spotify ID or URI of the playlist
        song_uris: List of Spotify song URIs (e.g. ['spotify:track:...', ...])
    """
    return add_tracks_to_playlist(playlist_id, song_uris)


@mcp.tool()
def add_movie_songs_to_playlist(playlist_id: str, movie_name: str, max_songs: int = 5) -> str:
    """Find songs for a specific movie on Spotify and add them directly to an existing playlist.
    
    Args:
        playlist_id: The Spotify ID of the existing playlist
        movie_name: Title of the movie
        max_songs: Maximum number of songs to add (default: 5)
    """
    try:
        sp = get_spotify_client()
        pid = playlist_id.split(":")[-1].split("/")[-1].split("?")[0]
        tracks = fetch_tracks_for_movie(sp, movie_name, max_songs=max_songs)
        if not tracks:
            return f"No songs found on Spotify for movie '{movie_name}'."

        uris = [t["uri"] for t in tracks]
        sp.playlist_add_items(playlist_id=pid, items=uris)
        titles = ", ".join(f"'{t['title']}'" for t in tracks)
        return f"Added {len(uris)} song(s) from '{movie_name}' to playlist {pid} (Total songs added: {len(uris)}): {titles}"
    except Exception as e:
        return f"Error adding movie songs to playlist: {str(e)}"


@mcp.tool()
def get_current_playback() -> str:
    """Get information about the user's current playback state, active song, and active device."""
    try:
        sp = get_spotify_client()
        playback = sp.current_playback()
        if not playback or not playback.get("item"):
            return "No song is currently playing or Spotify is inactive."

        item = playback["item"]
        song_name = item.get("name", "Unknown Song")
        artists = ", ".join(artist["name"] for artist in item.get("artists", []))
        album = item.get("album", {}).get("name", "Unknown Album")
        is_playing = playback.get("is_playing", False)
        progress_ms = playback.get("progress_ms", 0)
        duration_ms = item.get("duration_ms", 0)
        device = playback.get("device", {}).get("name", "Unknown Device")
        volume = playback.get("device", {}).get("volume_percent", "N/A")

        progress_sec = progress_ms // 1000
        duration_sec = duration_ms // 1000

        return (
            f"Status: {'Playing' if is_playing else 'Paused'}\n"
            f"Song: {song_name}\n"
            f"Artist(s): {artists}\n"
            f"Album: {album}\n"
            f"Progress: {progress_sec // 60}:{progress_sec % 60:02d} / {duration_sec // 60}:{duration_sec % 60:02d}\n"
            f"Device: {device} (Volume: {volume}%)\n"
            f"Song URI: {item.get('uri', '')}"
        )
    except Exception as e:
        return f"Error fetching current playback: {str(e)}"


@mcp.tool()
def play_track(uri: Optional[str] = None, context_uri: Optional[str] = None) -> str:
    """Resume playback or play a specific song/album/playlist by URI.
    
    Args:
        uri: Spotify song URI (e.g. 'spotify:track:...')
        context_uri: Spotify album, artist, or playlist URI (e.g. 'spotify:playlist:...')
    """
    try:
        sp = get_spotify_client()
        if uri:
            sp.start_playback(uris=[uri])
            return f"Started playback for song: {uri}"
        elif context_uri:
            sp.start_playback(context_uri=context_uri)
            return f"Started playback for context: {context_uri}"
        else:
            sp.start_playback()
            return "Resumed playback."
    except Exception as e:
        return f"Error playing: {str(e)}"


@mcp.tool()
def play_song(uri: Optional[str] = None, context_uri: Optional[str] = None) -> str:
    """Resume playback or play a specific song/album/playlist by URI."""
    return play_track(uri=uri, context_uri=context_uri)


@mcp.tool()
def pause_playback() -> str:
    """Pause the current Spotify playback."""
    try:
        sp = get_spotify_client()
        sp.pause_playback()
        return "Playback paused."
    except Exception as e:
        return f"Error pausing playback: {str(e)}"


@mcp.tool()
def next_track() -> str:
    """Skip to the next song in the queue."""
    try:
        sp = get_spotify_client()
        sp.next_track()
        return "Skipped to next song."
    except Exception as e:
        return f"Error skipping to next song: {str(e)}"


@mcp.tool()
def next_song() -> str:
    """Skip to the next song in the queue."""
    return next_track()


@mcp.tool()
def previous_track() -> str:
    """Skip to the previous song."""
    try:
        sp = get_spotify_client()
        sp.previous_track()
        return "Skipped to previous song."
    except Exception as e:
        return f"Error skipping to previous song: {str(e)}"


@mcp.tool()
def previous_song() -> str:
    """Skip to the previous song."""
    return previous_track()


@mcp.tool()
def set_volume(volume_percent: int) -> str:
    """Set the playback volume.
    
    Args:
        volume_percent: Volume level between 0 and 100.
    """
    if not (0 <= volume_percent <= 100):
        return "Volume percent must be between 0 and 100."
    try:
        sp = get_spotify_client()
        sp.volume(volume_percent)
        return f"Volume set to {volume_percent}%."
    except Exception as e:
        return f"Error setting volume: {str(e)}"


@mcp.tool()
def search_spotify(query: str, search_type: str = "track", limit: int = 5) -> str:
    """Search for songs, albums, artists, or playlists on Spotify.
    
    Args:
        query: Search keywords
        search_type: Types to search for (comma-separated: 'track', 'album', 'artist', 'playlist')
        limit: Number of results (default 5, max 20)
    """
    try:
        sp = get_spotify_client()
        results = sp.search(q=query, type=search_type, limit=min(limit, 20))
        lines = [f"Search results for '{query}':"]

        if "tracks" in results and results["tracks"]["items"]:
            items = results["tracks"]["items"]
            lines.append(f"\nSongs (Total count: {len(items)}):")
            for t in items:
                artists = ", ".join(a["name"] for a in t["artists"])
                lines.append(f"- {t['name']} by {artists} (URI: {t['uri']})")

        if "albums" in results and results["albums"]["items"]:
            items = results["albums"]["items"]
            lines.append(f"\nAlbums (Total count: {len(items)}):")
            for a in items:
                artists = ", ".join(art["name"] for art in a["artists"])
                lines.append(f"- {a['name']} by {artists} (URI: {a['uri']})")

        if "artists" in results and results["artists"]["items"]:
            items = results["artists"]["items"]
            lines.append(f"\nArtists (Total count: {len(items)}):")
            for art in items:
                lines.append(f"- {art['name']} (URI: {art['uri']}, Followers: {art.get('followers', {}).get('total', 0):,})")

        if "playlists" in results and results["playlists"]["items"]:
            items = [p for p in results["playlists"]["items"] if p]
            lines.append(f"\nPlaylists (Total count: {len(items)}):")
            for p in items:
                lines.append(f"- {p['name']} by {p.get('owner', {}).get('display_name', 'Unknown')} (URI: {p['uri']})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching Spotify: {str(e)}"


@mcp.tool()
def add_to_queue(uri: str) -> str:
    """Add a song to the user's playback queue.
    
    Args:
        uri: Spotify song or episode URI (e.g., 'spotify:track:...')
    """
    try:
        sp = get_spotify_client()
        sp.add_to_queue(uri)
        return f"Added song {uri} to playback queue."
    except Exception as e:
        return f"Error adding to queue: {str(e)}"


@mcp.tool()
def get_user_playlists(limit: int = 10) -> str:
    """Get the current user's playlists with song counts.
    
    Args:
        limit: Number of playlists to fetch (default 10, max 50)
    """
    try:
        sp = get_spotify_client()
        results = sp.current_user_playlists(limit=min(limit, 50))
        items = results.get("items", [])
        if not items:
            return "No playlists found."
        lines = [f"User Playlists (Total found: {len(items)}):"]
        for p in items:
            song_count = p.get('tracks', {}).get('total', 0)
            lines.append(f"- {p['name']} ({song_count} songs) [URI: {p['uri']}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching playlists: {str(e)}"


@mcp.tool()
def get_user_top_tracks(limit: int = 10, time_range: str = "medium_term") -> str:
    """Get the current user's top songs over a specified period.
    
    Args:
        limit: Number of songs (default 10, max 50)
        time_range: Over what time frame ('short_term' = ~4 weeks, 'medium_term' = ~6 months, 'long_term' = years)
    """
    try:
        sp = get_spotify_client()
        results = sp.current_user_top_tracks(limit=min(limit, 50), time_range=time_range)
        items = results.get("items", [])
        if not items:
            return "No top songs found."
        lines = [f"Top Songs ({time_range}) - Total count: {len(items)}:"]
        for idx, t in enumerate(items, 1):
            artists = ", ".join(a["name"] for a in t["artists"])
            lines.append(f"{idx}. {t['name']} - {artists} (URI: {t['uri']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching top songs: {str(e)}"


@mcp.tool()
def get_user_top_songs(limit: int = 10, time_range: str = "medium_term") -> str:
    """Get the current user's top songs over a specified period."""
    return get_user_top_tracks(limit=limit, time_range=time_range)


# =====================================================================
# Integrated Web App (Soundtrack Curator & Staging Studio)
# =====================================================================

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
                web_server_file = Path(__file__).parent / "mcp-soundtrack-app" / "server.py"
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


@mcp.tool()
def open_soundtrack_studio() -> str:
    """Launch or retrieve the URL for the Soundtrack Curator & Staging Studio web application.
    
    Returns the local web application URL and opens it in your default browser.
    """
    port = start_background_web_app(default_port=8000, open_browser=True)
    url = f"http://127.0.0.1:{port}"
    return f"Soundtrack Curator & Staging Studio is running at {url}. Opened in your default browser!"


if __name__ == "__main__":
    import threading
    auto_open = os.getenv("OPEN_BROWSER", "true").strip().lower() not in ("0", "false", "no")
    start_background_web_app(default_port=8000, open_browser=auto_open)
    try:
        mcp.run()
    except KeyboardInterrupt:
        pass

