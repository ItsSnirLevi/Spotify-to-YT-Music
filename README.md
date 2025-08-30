# Spotify → YouTube Music Transfer

A Python script to copy **Spotify playlists (including Liked Songs)** into **YouTube Music**.

---

## Features
- Transfers all or selected playlists from Spotify to YouTube Music
- Treats **Liked Songs** as a playlist called *Liked Songs*
- Resumable & idempotent via `transfer_state.json`
- Track matching by title, artist, and duration
- Robust batch adding with retries and failure report (`ytm_add_failures.csv`)

---

## Requirements

- Python 3.10+
- A Spotify Developer application (for API access)
- A Google Cloud project with **YouTube Data API v3** enabled and OAuth client credentials created (type: *TVs and Limited Input devices*)

---

## Setup

### 1. Clone and install dependencies
```bash
git clone https://github.com/<you>/spotify-ytmusic-transfer.git
cd spotify-ytmusic-transfer
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Spotify Developer App
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and **Create app**.
2. Under *Redirect URIs* add:
   ```
   http://127.0.0.1:8080/callback
   ```
   (⚠️ Use `127.0.0.1`, not `localhost` — Spotify deprecated localhost.)
3. Copy **Client ID** and **Client Secret**.
4. Create a `.env` file from `.env.example` and fill in:
   ```ini
   SPOTIPY_CLIENT_ID=your_client_id
   SPOTIPY_CLIENT_SECRET=your_client_secret
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback
   ```

### 3. YouTube Music OAuth Setup
1. In [Google Cloud Console](https://console.cloud.google.com/), enable **YouTube Data API v3**.
2. Configure **OAuth consent screen** (External, add yourself as a *Test User*).
3. Create **OAuth client credentials** with type *TVs and Limited Input devices*.
4. Install `ytmusicapi` if not already:  
   ```bash
   pip install ytmusicapi
   ```
5. Run the device flow:
   ```bash
   ytmusicapi oauth
   ```
   - Paste your `client_id` and `client_secret` from the Cloud Console
   - Complete the device login flow
   - A file `oauth.json` will be created
6. Set an environment variable pointing to it (or place it in `~/oauth.json`):
   ```bash
   export YTMUSIC_OAUTH=/path/to/oauth.json
   ```
   You can also add to `.env`:
   ```ini
   YTMUSIC_OAUTH=/path/to/oauth.json
   YTMUSIC_CLIENT_ID=your_google_client_id
   YTMUSIC_CLIENT_SECRET=your_google_client_secret
   ```

---

## Running

Transfer everything (all playlists + Liked Songs):
```bash
python spotify_to_ytm.py
```

Transfer only specific playlists:
```bash
INCLUDE_PLAYLISTS="Liked Songs, Roadtrip" python spotify_to_ytm.py
```

Exclude certain playlists:
```bash
EXCLUDE_PLAYLISTS="Discover Weekly, Release Radar" python spotify_to_ytm.py
```

---

## Outputs

- Creates playlists in YouTube Music (private by default)
- Progress printed to console
- Writes `transfer_state.json` for resumability
- Writes `ytm_add_failures.csv` listing rejected/missing items

---

## Troubleshooting

**403 Insufficient client scope (Spotify):**  
Delete `.spotipy_cache` and rerun. Make sure `user-library-read` is in your scopes.

**Invalid redirect URI (Spotify):**  
Must exactly match `http://127.0.0.1:8080/callback` in both code and dashboard.

**YouTube Music errors about `oauth_credentials`:**  
Ensure you’re using an `OAuthCredentials` object. Re-run `ytmusicapi oauth` and set `YTMUSIC_OAUTH` properly.

**Playlist counts differ between Spotify and YTM:**  
- YT Music deduplicates songs
- Some songs unavailable in your region
- Some “added” videos are hidden/unplayable

---

## Security

⚠️ **Never commit secrets or tokens** (`.env`, `oauth.json`, `.spotipy_cache`, `transfer_state.json`).  
Use `.gitignore` provided.

---

## License

MIT License © 2025
