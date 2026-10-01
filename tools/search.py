from typing import Optional, List, Dict, Any
from mcp.types import ToolAnnotations
from tools.core import mcp, get_spotify_client
import spotipy

from tools.tmdb_helpers import *

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


