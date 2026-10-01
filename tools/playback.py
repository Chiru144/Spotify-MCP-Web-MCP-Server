from typing import Optional, List, Dict, Any
from mcp.types import ToolAnnotations
from tools.core import mcp, get_spotify_client
import spotipy

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def play_track(
    device_id: Optional[str] = None,
    context_uri: Optional[str] = None,
    uris: Optional[list[str]] = None,
    uri: Optional[str] = None,
    offset_position: Optional[int] = None,
    position_ms: Optional[int] = None,
) -> str:
    """Start or resume playback.
    Args:
        device_id: ID of the device to play on. Uses active device if omitted.
        context_uri: Spotify URI of context (album, artist, playlist).
        uris: List of Spotify track URIs to play. E.g. ["spotify:track:xxx"].
        uri: Single track URI (for backward compatibility).
        offset_position: Position in the context to start playback (0-based index).
        position_ms: Position in milliseconds to seek to.
    """
    try:
        sp = get_spotify_client()
        
        # Consolidate uri/uris
        if uri and not uris:
            uris = [uri]

        kwargs = {}
        if context_uri:
            kwargs["context_uri"] = context_uri
        if uris:
            kwargs["uris"] = uris
        if offset_position is not None:
            kwargs["offset"] = {"position": offset_position}
        if position_ms is not None:
            kwargs["position_ms"] = position_ms
            
        # Try playback
        try:
            sp.start_playback(device_id=device_id, **kwargs)
            return "Playback started/resumed."
        except spotipy.exceptions.SpotifyException as e:
            # If 404 and no device_id was forced, attempt to find an active/fallback device
            if e.http_status == 404 and not device_id:
                devices = sp.devices().get('devices', [])
                if not devices:
                    return "Error: No active devices found."
                fallback_id = None
                for d in devices:
                    if d.get('is_active'):
                        fallback_id = d.get('id')
                        break
                if not fallback_id:
                    fallback_id = next((d.get('id') for d in devices if d.get('type') == 'Computer'), devices[0].get('id'))
                
                sp.start_playback(device_id=fallback_id, **kwargs)
                return "Playback started/resumed on fallback device."
            raise e
            
    except Exception as e:
        return f"Error playing: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def play_song(uri: Optional[str] = None, context_uri: Optional[str] = None) -> str:
    """Resume playback or play a specific song/album/playlist by URI."""
    return play_track(uri=uri, context_uri=context_uri)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def pause_playback() -> str:
    """Pause the current Spotify playback."""
    try:
        sp = get_spotify_client()
        sp.pause_playback()
        return "Playback paused."
    except Exception as e:
        return f"Error pausing playback: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def next_track() -> str:
    """Skip to the next song in the queue."""
    try:
        sp = get_spotify_client()
        sp.next_track()
        return "Skipped to next song."
    except Exception as e:
        return f"Error skipping to next song: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def next_song() -> str:
    """Skip to the next song in the queue."""
    return next_track()


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def previous_track() -> str:
    """Skip to the previous song."""
    try:
        sp = get_spotify_client()
        sp.previous_track()
        return "Skipped to previous song."
    except Exception as e:
        return f"Error skipping to previous song: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
def previous_song() -> str:
    """Skip to the previous song."""
    return previous_track()


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def seek_playback(position_ms: int) -> str:
    """Seeks to the given position in the user's currently playing track.
    
    Args:
        position_ms: The position in milliseconds to seek to.
    """
    try:
        sp = get_spotify_client()
        sp.seek_track(position_ms)
        return f"Playback sought to {position_ms} ms."
    except Exception as e:
        return f"Error seeking playback: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def set_repeat_mode(state: str) -> str:
    """Set the repeat mode for the user's playback.
    
    Args:
        state: 'track', 'context', or 'off'.
    """
    if state not in ['track', 'context', 'off']:
        return "State must be 'track', 'context', or 'off'."
    try:
        sp = get_spotify_client()
        sp.repeat(state)
        return f"Repeat mode set to {state}."
    except Exception as e:
        return f"Error setting repeat mode: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def set_shuffle(state: bool) -> str:
    """Toggle shuffle for the user's playback.
    
    Args:
        state: True to turn shuffle on, False to turn it off.
    """
    try:
        sp = get_spotify_client()
        sp.shuffle(state)
        return f"Shuffle turned {'on' if state else 'off'}."
    except Exception as e:
        return f"Error setting shuffle: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def get_available_devices() -> str:
    """Get information about a user's available devices."""
    try:
        sp = get_spotify_client()
        devices = sp.devices().get('devices', [])
        if not devices:
            return "No available devices found."
        lines = ["Available Devices:"]
        for d in devices:
            active = "(Active)" if d.get('is_active') else ""
            lines.append(f"- {d.get('name')} [{d.get('type')}] ID: {d.get('id')} {active}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching devices: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def transfer_playback(device_id: str, play: bool = False) -> str:
    """Transfer playback to a new device.
    
    Args:
        device_id: The ID of the device to transfer playback to.
        play: Whether to ensure playback happens on the new device.
    """
    try:
        sp = get_spotify_client()
        sp.transfer_playback(device_id, force_play=play)
        return f"Playback transferred to device {device_id}."
    except Exception as e:
        return f"Error transferring playback: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
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


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def get_queue() -> str:
    """Get the user's current playback queue."""
    try:
        sp = get_spotify_client()
        queue = sp.queue()
        currently_playing = queue.get('currently_playing')
        queue_items = queue.get('queue', [])
        
        lines = []
        if currently_playing:
            lines.append(f"Currently Playing: {currently_playing.get('name')} by {', '.join(a['name'] for a in currently_playing.get('artists', []))}")
        
        if not queue_items:
            lines.append("Queue is empty.")
        else:
            lines.append(f"\nUp Next (Total: {len(queue_items)}):")
            for idx, item in enumerate(queue_items[:20], 1):
                lines.append(f"{idx}. {item.get('name')} by {', '.join(a['name'] for a in item.get('artists', []))} (URI: {item.get('uri')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching queue: {str(e)}"


