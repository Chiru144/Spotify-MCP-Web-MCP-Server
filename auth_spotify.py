"""One-click Spotify OAuth Authentication Script.
Runs Spotipy's local auth server on http://127.0.0.1:8888/callback,
opens your browser for approval, and caches the user token.
"""
import os
import sys
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / ".env"
from dotenv import load_dotenv
load_dotenv(dotenv_path=env_path)

from server import SPOTIFY_SCOPES, get_spotify_client


def main():
    print("=" * 65)
    print(" Spotify Account Authorization Helper")
    print("=" * 65)
    print("\nStarting Spotify authentication flow...")
    print("Your browser should open automatically.")
    print("If it does not, copy the link shown and paste it into your browser.\n")
    
    try:
        sp = get_spotify_client()
        user = sp.current_user()
        print("=" * 65)
        print(" [SUCCESS] Successfully authenticated with Spotify!")
        print("=" * 65)
        print(f" Logged in as: {user.get('display_name')} (ID: {user.get('id')})")
        print(f" Email:        {user.get('email', 'N/A')}")
        print(f" Product:      {user.get('product', 'free/premium')}")
        print(f" Country:      {user.get('country', 'N/A')}")
        print("=" * 65)
        print("\nToken saved to .spotipyoauthcache.")
        print("Both your MCP server and the Soundtrack App are ready to use!\n")
    except Exception as e:
        print("\n" + "!" * 65)
        print(f" [ERROR] Authentication failed: {e}")
        print("!" * 65)
        print("\nTroubleshooting tips:")
        print("1. Check Spotify Developer Dashboard (https://developer.spotify.com/dashboard):")
        print("   - Open your App -> Click 'Settings'")
        print("   - Under 'Redirect URIs', ensure 'http://127.0.0.1:8888/callback' is added.")
        print("2. Check User Management:")
        print("   - If your app is in 'Development Mode', make sure the Spotify email")
        print("     you are logging into is added under 'User Management' / 'Users and Access'.\n")


if __name__ == "__main__":
    main()
