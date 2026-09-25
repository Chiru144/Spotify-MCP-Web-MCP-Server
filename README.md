# Spotify & TMDB Web MCP Server

This repository contains a FastMCP application that integrates Spotify and TMDB (The Movie Database). It allows you to build custom soundtracks and interact with a web-based Soundtrack Curator & Staging Studio.

## Features

- **Full Playback Control**: Play, pause, skip tracks, adjust volume, and manage your queue directly through chat.
- **Playlist Management**: Create new playlists, add songs, shuffle, combine multiple playlists, and remove duplicates.
- **Search & Library Access**: Search for tracks, albums, artists, or playlists on Spotify, and access your saved playlists.
- **Personal Listening Insights**: Retrieve your top played songs across different time periods (short, medium, or long term).
- **TMDB Movie & Actor Search**: Look up rich biographical profiles for actors or get release details, overviews, and ratings for movies directly from The Movie Database.
- **Soundtrack Curator**: Integrated with TMDB and DuckDuckGo to automatically discover an actor's filmography, find the corresponding soundtracks, and build a dedicated Spotify playlist.
- **Soundtrack Staging Studio**: A local web interface to visualize and manage your curated soundtracks.

## Prerequisites

Before running the application, make sure you have the following installed:
- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/)

You will also need Developer API Keys for:
- [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
- [TMDB API](https://developer.themoviedb.org/docs/getting-started)

## Installation & Setup

Follow these steps to get the project running locally:

### 1. Clone the repository

```bash
git clone https://github.com/Chiru144/Spotify-MCP-Web-MCP-Server.git
cd Spotify-MCP-Web-MCP-Server
```

### 2. Create and activate a Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the required Python packages from the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a file named `.env` in the root of the project directory. You need to add your API credentials from Spotify and TMDB.

Here is the `.env` template:

```ini
# Spotify Credentials
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=http://localhost:8080 # Or your configured redirect URI

# Alternative Spotify keys (if used in the app)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8080 

# TMDB Credentials
TMDB_API_KEY=your_tmdb_api_key
TMDB_READ_ACCESS_TOKEN=your_tmdb_read_access_token
TMDB_ACCESS_TOKEN=your_tmdb_access_token

# Optional configuration
OPEN_BROWSER=true
```

Make sure to replace `your_*` placeholders with the actual keys from your developer dashboards.

## Running the Application

There are two entry points to run the server, depending on your use case:

### 1. `server.py` (Development & Web App Focus)

Start the MCP server and background web app simultaneously by running:

```bash
python server.py
```

The application will start, and the web interface should automatically open in your default browser at `http://127.0.0.1:8000`.

### 2. `mcp.py` (MCP Client Integration Focus)

If you are running this project as a tool inside an MCP host (like Cursor, VSCode, or Claude Desktop), you should use `mcp.py`:

```bash
python mcp.py
```

**Why `mcp.py`?** Standard MCP uses standard input/output (`stdio`) for communication. When Spotify requires you to log in for the first time, it normally pauses and asks you to paste a redirect URL in the terminal. This breaks the MCP protocol. `mcp.py` solves this by launching a **Tkinter GUI popup** for the Spotify authentication process, ensuring `stdio` remains clean and unblocked for the MCP client.

## API Limits

Please keep in mind the rate limits imposed by the external APIs used in this project:

- **Spotify Web API**: Spotify uses a dynamic rate limit based on a rolling window. If you make too many requests in a short period (such as aggressively searching or curating massive playlists), you will receive a `429 Too Many Requests` response. The app may need to back off and try again later.
- **TMDB API**: The Movie Database allows up to **50 requests per second**. This is generally quite generous for normal usage, but batch queries or rapid concurrent lookups could potentially hit this limit.

## MCP Integration

This project is built using `fastmcp`. Once running via `stdio` (or SSE if configured), it can be seamlessly consumed by other MCP clients.
