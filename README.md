# Spotify → YouTube Music Transfer

A Python tool to migrate your Spotify playlists — including **Liked Songs** — to YouTube Music.

- Reads all or selected playlists from Spotify
- Creates/updates matching playlists on YouTube Music
- Matches by **title + artists + duration**, prefers “song” results
- **Resumable & idempotent** with a state cache
- Post-add **healing pass**: re-searches alternatives for missing/duped items
- **Compare mode** to diff same-named playlists across Spotify and YTM
- CSV reports for failures and diffs

---

## 1) Prerequisites

- Python **3.10+**
- A Spotify developer app (Client ID/Secret)
- A Google Cloud project with an **OAuth client of type “TVs and Limited Input devices”**  
  and **YouTube Data API v3** enabled  
- `ytmusicapi` OAuth file (`oauth.json`) generated with your Google OAuth client

---

## 2) Setup

```bash
git clone <your-repo-url>
cd <repo>
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in your keys (see below).

### Spotify app setup
1. https://developer.spotify.com/dashboard → **Create app**
2. Add redirect URI: `http://127.0.0.1:8080/callback`
3. Put **Client ID/Secret** in `.env`:
   - `SPOTIPY_CLIENT_ID`
   - `SPOTIPY_CLIENT_SECRET`
   - (optional) `SPOTIPY_REDIRECT_URI` — defaults to `http://127.0.0.1:8080/callback`

### YouTube Music OAuth (via `ytmusicapi`)
1. In Google Cloud Console:
   - Create an OAuth client: **TVs and Limited Input devices**
   - Enable **YouTube Data API v3**
   - Note the **Client ID/Secret** and put in `.env`:
     - `YTMUSIC_CLIENT_ID`
     - `YTMUSIC_CLIENT_SECRET`
2. Generate the device OAuth file with `ytmusicapi`:
   ```bash
   # This opens a device code flow; authenticate with your Google account
   ytmusicapi oauth --client-id "$YTMUSIC_CLIENT_ID" --client-secret "$YTMUSIC_CLIENT_SECRET" --oauth-file oauth.json
   ```
3. Point the script to that file via:
   - `YTMUSIC_OAUTH=./oauth.json` (or an absolute path)

> The script **requires** the `oauth.json` plus the `YTMUSIC_CLIENT_ID/SECRET` to refresh tokens.

---

## 3) Configure via `.env`

See `.env.example` for all options:

- **Required (Spotify)**
  - `SPOTIPY_CLIENT_ID`
  - `SPOTIPY_CLIENT_SECRET`
  - `SPOTIPY_REDIRECT_URI` (recommended: `http://127.0.0.1:8080/callback`)

- **Required (YouTube Music)**
  - `YTMUSIC_CLIENT_ID`
  - `YTMUSIC_CLIENT_SECRET`
  - `YTMUSIC_OAUTH` (path to the `oauth.json` you generated)

- **Optional filters**
  - `INCLUDE_PLAYLISTS` — comma-separated names to transfer/compare (e.g. `Liked Songs,Vibes`)
  - `EXCLUDE_PLAYLISTS` — comma-separated names to skip
  - `COMPARE_ONLY` — set to `1/true/yes` to run comparison without transferring

> The special playlist name **`Liked Songs`** represents your Spotify saved tracks.

---

## 4) Run

### Transfer (default)
```bash
python spotify_to_ytm.py
```

**Filter examples**
```bash
INCLUDE_PLAYLISTS="Liked Songs,Vibes" python spotify_to_ytm.py
EXCLUDE_PLAYLISTS="Old Mix" python spotify_to_ytm.py
```

### Compare only (no changes, just CSV diffs)
```bash
COMPARE_ONLY=1 python spotify_to_ytm.py
```

---

## 5) What the script does

1. Logs into Spotify & YTM.
2. Builds a list of playlists (plus a pseudo-playlist for **Liked Songs**).
3. For each playlist:
   - Searches YTM for each Spotify track (title+artist+duration scoring).
   - **Pre-dedupes** items already in the target YTM playlist.
   - Adds tracks in small batches.
   - **Verifies** what actually landed and runs a **healing pass** to find alternative matches for:
     - missing/unavailable items
     - duplicates where multiple Spotify tracks mapped to the same `videoId`

---

## 6) Outputs & Reports

- `transfer_state.json` — cache for resumability and improved next runs
- `ytm_add_failures.csv` — any items YTM explicitly rejected
- `missing_in_ytm_<playlist>.csv` — on Spotify but not on YTM
- `missing_in_spotify_<playlist>.csv` — on YTM but not on Spotify (often different versions)

---

## 7) Tips & Troubleshooting

- **403 Insufficient client scope (Spotify)**: ensure scopes include  
  `playlist-read-private playlist-read-collaborative user-library-read`
- **Not enough items added (YT Music)**:
  - YTM dedupes identical `videoId`s.
  - Some `videoId`s may be region-locked/unavailable.
  - The script’s **healing pass** tries cleaned title queries and alternates.
- **Change only a few playlists**: use `INCLUDE_PLAYLISTS` or `EXCLUDE_PLAYLISTS`.
- **Reruns are safe**: the script is idempotent and uses the cache to avoid rematching every time.

---

## 8) License
MIT ©
