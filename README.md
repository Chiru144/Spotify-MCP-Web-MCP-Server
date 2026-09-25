# Spotify & TMDB Web MCP Server

This repository contains a FastMCP application that integrates Spotify and TMDB (The Movie Database). It allows you to build custom soundtracks and interact with a web-based Soundtrack Curator & Staging Studio.

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

Start the MCP server and background web app by running:

```bash
python server.py
```

The application will start, and the web interface should automatically open in your default browser at `http://127.0.0.1:8000`.

## MCP Integration

This project is built using `fastmcp`. Once running, it can be consumed by other MCP clients. 
