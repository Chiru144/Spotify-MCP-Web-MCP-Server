from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
from tools.core import get_spotify_client
import spotipy

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

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


