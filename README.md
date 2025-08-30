# Spotify → YouTube Music Transfer

Copy **all or selected** Spotify playlists — including **Liked Songs** — to **YouTube Music**.

- Matches by title/artist (+ duration) with retries
- Treats **Liked Songs** as a regular playlist
- Resumable & idempotent via `transfer_state.json`
- CLI usage with environment variables

> ⚠️ Never commit credentials (`.env`, `oauth.json`, `.spotipy_cache`, `transfer_state.json`).

---

## 1) Setup

### Create and activate a virtualenv
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Spotify Developer app
1. Go to https://developer.spotify.com/dashboard → **Create app**.
2. Add Redirect URI: `http://127.0.0.1:8080/callback`.
3. Copy **Client ID** and **Client Secret**.
4. Copy `.env.example` to `.env` and fill values:
   ```env
   SPOTIPY_CLIENT_ID=...
   SPOTIPY_CLIENT_SECRET=...
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback
   ```
5. First run will open a browser to grant scopes:
   - `playlist-read-private`, `playlist-read-collaborative`, `user-library-read`

### YouTube Music OAuth (Google)
1. In **Google Cloud Console**, enable **YouTube Data API v3**.
2. Configure **OAuth consent screen** → type **External** → add yourself under **Test users**.
3. **Credentials** → **Create credentials** → **OAuth client ID** → *TVs and Limited Input devices*.
4. Run device flow to create `oauth.json`:
   ```bash
   ytmusicapi oauth
   ```
   Then set `YTMUSIC_OAUTH` in your `.env` if you don't put it at `~/oauth.json`.

---

## 2) Run

```bash
# Transfer everything (all playlists + Liked Songs)
python spotify_to_ytm.py

# Only selected playlists (comma-separated exact names)
INCLUDE_PLAYLISTS="Liked Songs, Vibes" python spotify_to_ytm.py

# Exclude specific playlists
EXCLUDE_PLAYLISTS="Discover Weekly, Release Radar" python spotify_to_ytm.py
```

### Notes
- Stop anytime with Ctrl+C; rerun resumes work without duplicating.
- After adding, the script prints: **attempted / added / failed** and current YTM playlist size.
- YTM can dedupe or hide unavailable tracks; final visible count may be lower than attempted.

---

## 3) Troubleshooting

**Spotify 403: Insufficient client scope**  
Delete `.spotipy_cache` and rerun to re-grant scopes.

**Invalid redirect URI**  
Ensure code and Spotify dashboard both use `http://127.0.0.1:8080/callback` exactly.

**YouTube auth errors**  
Re-run `ytmusicapi oauth` to regenerate a full `oauth.json` (with client_id/secret + refresh_token). Ensure YouTube Data API v3 is enabled and your account is a Test user.

---

## 4) Security
- Keep secrets out of Git; see `.gitignore`.
- Consider separate Google projects for testing vs personal use.
