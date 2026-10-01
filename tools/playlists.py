from typing import Optional, List, Dict, Any
from mcp.types import ToolAnnotations
from tools.core import mcp, get_spotify_client
import spotipy

from tools.tmdb_helpers import *

@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def add_songs_to_playlist(playlist_id: str, song_uris: List[str]) -> str:
    """Add a list of Spotify song URIs to an existing playlist.
    
    Args:
        playlist_id: The Spotify ID or URI of the playlist
        song_uris: List of Spotify song URIs (e.g. ['spotify:track:...', ...])
    """
    return add_tracks_to_playlist(playlist_id, song_uris)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def reorder_playlist_by_audio_features(playlist_id: str, feature: str = 'energy', order: str = 'desc') -> str:
    """Smart Reorder: Sorts a user's playlist by a given audio feature (energy, valence, danceability, etc).
    
    Args:
        playlist_id: Spotify playlist ID or URI.
        feature: The audio feature to sort by (e.g., 'energy', 'valence', 'danceability', 'tempo').
        order: 'asc' for ascending, 'desc' for descending.
    """
    if feature not in ['energy', 'valence', 'danceability', 'tempo', 'acousticness', 'instrumentalness', 'liveness', 'speechiness']:
        return "Unsupported feature. Use energy, valence, danceability, tempo, etc."
    try:
        sp = get_spotify_client()
        # get all tracks
        results = sp.playlist_tracks(playlist_id)
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
            
        # extract valid tracks
        track_uris = [item['track']['uri'] for item in tracks if item.get('track') and item['track']['uri']]
        if not track_uris:
            return "No tracks found in playlist."
            
        # fetch features in chunks of 100
        features = []
        for i in range(0, len(track_uris), 100):
            batch = sp.audio_features(track_uris[i:i+100])
            features.extend(batch)
            
        # pair and sort
        track_data = []
        for i, feat in enumerate(features):
            if feat is not None:
                track_data.append({'uri': track_uris[i], 'val': feat.get(feature, 0)})
            else:
                track_data.append({'uri': track_uris[i], 'val': 0})
                
        track_data.sort(key=lambda x: x['val'], reverse=(order == 'desc'))
        sorted_uris = [t['uri'] for t in track_data]
        
        # apply changes by replacing entire playlist tracks in batches of 100
        if sorted_uris:
            sp.playlist_replace_items(playlist_id, sorted_uris[:100])
            for i in range(100, len(sorted_uris), 100):
                sp.playlist_add_items(playlist_id, sorted_uris[i:i+100])
                
        return f"Playlist successfully reordered by {feature} in {order}ending order."
    except Exception as e:
        return f"Error reordering playlist: {str(e)}"


@mcp.tool()
def update_playlist(playlist_id: str, name: Optional[str] = None, description: Optional[str] = None, public: Optional[bool] = None) -> str:
    """Update a playlist's name, description, or public status."""
    try:
        sp = get_spotify_client()
        kwargs = {}
        if name is not None:
            kwargs["name"] = name
        if description is not None:
            kwargs["description"] = description
        if public is not None:
            kwargs["public"] = public
        sp.playlist_change_details(playlist_id, **kwargs)
        return f"Successfully updated playlist {playlist_id}."
    except Exception as e:
        return f"Error updating playlist: {str(e)}"


@mcp.tool()
def get_playlist_tracks(playlist_id: str, limit: int = 100, offset: int = 0) -> str:
    """Get the tracks currently inside a specific playlist."""
    try:
        sp = get_spotify_client()
        results = sp.playlist_items(playlist_id, limit=limit, offset=offset)
        items = results.get("items", [])
        if not items:
            return "No tracks found in this playlist."
        output = [f"Playlist tracks (offset {offset}):"]
        for i, item in enumerate(items, 1):
            t = item.get("track", {})
            if not t:
                continue
            artists = ", ".join([a.get("name", "Unknown") for a in t.get("artists", [])])
            output.append(f"{i}. {t.get('name')} by {artists} (URI: {t.get('uri')})")
        return "\n".join(output)
    except Exception as e:
        return f"Error fetching playlist tracks: {str(e)}"


@mcp.tool()
def remove_tracks_from_playlist(playlist_id: str, uris: list[str]) -> str:
    """Remove one or more tracks from a playlist by their URIs."""
    try:
        sp = get_spotify_client()
        # Spotify API accepts up to 100 tracks per request
        for i in range(0, len(uris), 100):
            batch = uris[i:i+100]
            sp.playlist_remove_all_occurrences_of_items(playlist_id, batch)
        return f"Successfully removed {len(uris)} tracks from playlist {playlist_id}."
    except Exception as e:
        return f"Error removing tracks from playlist: {str(e)}"


