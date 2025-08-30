#!/usr/bin/env python3
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    # Prefer OAuth if available
    from ytmusicapi import YTMusic

    # For current ytmusicapi, oauth_credentials must be an OAuthCredentials object
    try:
        from ytmusicapi.auth.oauth import OAuthCredentials  # modern versions
    except ImportError:
        from ytmusicapi import OAuthCredentials  # fallback for older builds
except ImportError:
    raise SystemExit("Install ytmusicapi: pip install ytmusicapi")

load_dotenv()

# ---------- Config ----------
SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
]  # Needed to read all your playlists

CACHE_FILE = "transfer_state.json"  # for resumability (maps Spotify track->YT video)

# Search knobs
MAX_SEARCH_CANDIDATES = 5  # how many YTM search results to consider
ACCEPTABLE_TITLE_FUZZ = 0.34  # how loose we allow title/artist match (0..1; lower=looser)
SLEEP_BETWEEN_ADDS = 0.10  # seconds, be nice to APIs

# Special ID we use in state mapping for Liked Songs
LIKED_SONGS_ID = "__LIKED_SONGS__"
LIKED_SONGS_NAME = "Liked Songs"


# ---------- Helpers ----------
def slug(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def normalize_track(title: str, artists: List[str]) -> str:
    a = ", ".join(artists)
    return slug(f"{title} — {a}")


def approx_ratio(a: str, b: str) -> float:
    # quick ratio without external deps
    from difflib import SequenceMatcher
    return SequenceMatcher(None, slug(a), slug(b)).ratio()


@dataclass
class Track:
    sp_id: str
    name: str
    artists: List[str]
    album: Optional[str]
    duration_ms: Optional[int]


# ---------- State persistence ----------
def load_state() -> Dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"playlist_map": {}, "track_map": {}}


def save_state(state: Dict) -> None:
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_FILE)


# ---------- Spotify ----------
def spotify_client() -> spotipy.Spotify:
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8080/callback")
    auth = SpotifyOAuth(
            scope=" ".join(SPOTIFY_SCOPES),
            client_id=os.environ.get("SPOTIPY_CLIENT_ID"),
            client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET"),
            redirect_uri=redirect_uri,  # loopback IP recommended
            open_browser=True,
            cache_path=".spotipy_cache",
            show_dialog=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def fetch_liked_songs(sp: spotipy.Spotify) -> List[Track]:
    tracks, resp = [], sp.current_user_saved_tracks(limit=50)
    while True:
        for it in resp["items"]:
            t = it.get("track")
            if not t or t.get("is_local"):
                continue
            tracks.append(
                    Track(
                            sp_id=t["id"],
                            name=t["name"],
                            artists=[a["name"] for a in (t.get("artists") or [])],
                            album=(t.get("album") or {}).get("name"),
                            duration_ms=t.get("duration_ms"),
                    )
            )
        if resp.get("next"):
            resp = sp.next(resp)
        else:
            break
    return tracks


def fetch_all_spotify_playlists(sp: spotipy.Spotify) -> List[dict]:
    items, resp = [], sp.current_user_playlists(limit=50)
    items.extend(resp["items"])
    while resp.get("next"):
        resp = sp.next(resp)
        items.extend(resp["items"])
    return items


def fetch_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[Track]:
    tracks, resp = [], sp.playlist_items(playlist_id, additional_types=("track",), limit=100)
    while True:
        for it in resp["items"]:
            t = it.get("track")
            if not t or t.get("is_local"):
                continue
            tracks.append(
                    Track(
                            sp_id=t["id"],
                            name=t["name"],
                            artists=[a["name"] for a in (t.get("artists") or [])],
                            album=(t.get("album") or {}).get("name"),
                            duration_ms=t.get("duration_ms"),
                    )
            )
        if resp.get("next"):
            resp = sp.next(resp)
        else:
            break
    return tracks


# ---------- YT Music ----------
def ytm_client() -> YTMusic:
    """
    Prefer oauth.json; fall back to browser.json (ytmusicapi browser auth).
    """
    oauth_path = os.environ.get("YTMUSIC_OAUTH", os.path.expanduser("~/oauth.json"))

    if os.path.exists(oauth_path):
        client_id = os.environ.get("YTMUSIC_CLIENT_ID")
        client_secret = os.environ.get("YTMUSIC_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise SystemExit(
                    "Set YTMUSIC_CLIENT_ID / YTMUSIC_CLIENT_SECRET env vars, or re-run `ytmusicapi oauth` "
                    "using your Google OAuth client (TV & Limited Input devices)."
            )

        creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
        return YTMusic(oauth_path, oauth_credentials=creds)

    # Legacy browser-headers auth (no OAuth refresh)
    if os.path.exists("browser.json"):
        return YTMusic("browser.json")

    raise SystemExit(
            "No oauth.json or browser.json found. "
            "Create OAuth credentials with `ytmusicapi oauth` and set YTMUSIC_OAUTH to its path, "
            "or place a browser.json (legacy headers) next to the script."
    )


@retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=6.0),
        retry=retry_if_exception_type(Exception),
)
def ytm_search_best_id(ytm: YTMusic, track: Track) -> Optional[str]:
    """
    Search YTM for a Spotify track and return a playable videoId.
    We prefer 'song' results, otherwise 'video'.
    """
    q = f"{track.name} {', '.join(track.artists)}"
    results = ytm.search(query=q, limit=MAX_SEARCH_CANDIDATES)
    # rank by type preference + fuzzy title/artist similarity + duration proximity
    best_id, best_score = None, -1.0
    for r in results:
        title = r.get("title") or ""
        artists = [a.get("name", "") for a in r.get("artists", [])]
        t_ratio = approx_ratio(title, track.name)
        a_ratio = max((approx_ratio(", ".join(artists), ", ".join(track.artists))), 0)

        # duration score if available
        dur_score = 0.0
        if track.duration_ms and r.get("duration"):
            # ytm returns "3:45" style
            parts = r["duration"].split(":")
            r_ms = (int(parts[0]) * 60 + int(parts[1])) * 1000 if len(parts) == 2 else None
            if r_ms:
                # 1.0 when within 5s, fades after ~45s
                diff = abs(track.duration_ms - r_ms) / 1000.0
                dur_score = max(0.0, 1.0 - (diff / 45.0))

        type_bonus = 0.25 if r.get("resultType") == "song" else 0.0
        score = (0.5 * t_ratio) + (0.35 * a_ratio) + (0.15 * dur_score) + type_bonus

        if score > best_score:
            # prefer a direct videoId; sometimes setVideoId is used
            candidate = r.get("videoId") or r.get("setVideoId")
            if candidate:
                best_id, best_score = candidate, score

    # sanity check: require minimum similarity
    return best_id if best_score >= (1.0 - ACCEPTABLE_TITLE_FUZZ) else None


def ensure_playlist(ytm: YTMusic, name: str, description: Optional[str]) -> str:
    # Try to find an existing playlist with the same name to make the script idempotent
    existing = ytm.get_library_playlists(limit=100)
    for p in existing:
        if slug(p.get("title")) == slug(name):
            return p["playlistId"]
    # Create new
    return ytm.create_playlist(title=name[:150], description=(description or "")[:1000], privacy_status="PRIVATE")


def add_tracks_batched(ytm: YTMusic, playlist_id: str, video_ids: list[str]) -> dict:
    """
    Add tracks robustly:
      - small batches
      - checks API responses
      - retries failed items individually
    Returns a summary dict with successes/failures.
    """
    import time

    BATCH = 50
    summary = {"attempted": len(video_ids), "added": 0, "failed": []}

    def add_chunk(chunk: list[str]) -> tuple[int, list[tuple[str, str]]]:
        """returns (num_added, [(vid, reason), ...failures])"""
        try:
            resp = ytm.add_playlist_items(playlist_id, chunk)
        except Exception as e:
            # whole chunk failed — mark all and back off
            return 0, [(vid, f"exception:{e}") for vid in chunk]

        # ytmusicapi responses vary; normalize
        failures: list[tuple[str, str]] = []
        added = 0

        # Newer versions: dict with playlistEditResults in a list of dicts
        # Older versions: may return simple {"status": "STATUS_SUCCEEDED"}.
        # We’ll assume success if we don’t see per-item errors.
        if isinstance(resp, dict):
            # Try to find per-item results if present
            per = []
            for k in ("playlistEditResults", "playlistEditResultsRaw", "responses"):
                if k in resp and isinstance(resp[k], list):
                    per = resp[k]
                    break
            if per:
                for i, r in enumerate(per):
                    ok = False
                    # A few possible success markers seen in the wild:
                    ok = (
                            (isinstance(r, dict) and r.get("status") in ("STATUS_SUCCEEDED", "OK"))
                            or (isinstance(r, dict) and r.get("playlistEditVideoAddedResultData"))
                    )
                    if ok:
                        added += 1
                    else:
                        reason = r.get("status") or r.get("error", {}).get("message") or "unknown"
                        failures.append((chunk[i], str(reason)))
            else:
                # No per-item info—assume success for the whole chunk
                added += len(chunk)
        else:
            # Unexpected type; be conservative
            failures.extend((vid, "unexpected_response_type") for vid in chunk)

        return added, failures

    # First pass: in batches
    pending = list(video_ids)
    for i in range(0, len(pending), BATCH):
        chunk = [vid for vid in pending[i:i + BATCH] if vid]
        if not chunk:
            continue
        added, fails = add_chunk(chunk)
        summary["added"] += added
        summary["failed"].extend(fails)
        time.sleep(0.2)  # be gentle

    # Retry failures one-by-one (helps when only a few in a chunk triggered)
    if summary["failed"]:
        retry_list = [vid for vid, _ in summary["failed"]]
        summary["failed"] = []  # reset; we’ll re-collect only final failures
        time.sleep(1.0)

        for vid in retry_list:
            added, fails = add_chunk([vid])
            summary["added"] += added
            summary["failed"].extend(fails)
            time.sleep(0.15)

    return summary


def get_playlist_size(ytm: YTMusic, playlist_id: str) -> int:
    """Fetch current playlist size (tries to read full listing)."""
    pl = ytm.get_playlist(playlist_id, limit=10000)
    # Some responses include "trackCount"; items length is more reliable.
    return len(pl.get("tracks", []))


# ---------- Main transfer ----------
def transfer_playlists(include: List[str], exclude: List[str]) -> None:
    sp = spotify_client()
    ytm = ytm_client()
    state = load_state()

    # Normalize include/exclude names for comparison
    include_set = {slug(n) for n in include} if include else set()
    exclude_set = {slug(n) for n in exclude} if exclude else set()

    me = sp.current_user()
    print(f"Logged in to Spotify as: {me['display_name']} ({me['id']})")

    # Build a list of "playlist-like" items including Liked Songs
    playlists = []

    # 1) Regular playlists
    for p in fetch_all_spotify_playlists(sp):
        playlists.append({
            "sp_id": p["id"],
            "name": p["name"],
            "description": (p.get("description") or "")[:1000],
            "is_liked": False,
        })

    # 2) Liked Songs as a pseudo-playlist
    playlists.append({
        "sp_id": LIKED_SONGS_ID,
        "name": LIKED_SONGS_NAME,
        "description": "Imported from Spotify Liked Songs",
        "is_liked": True,
    })

    print(f"Found {len(playlists) - 1} Spotify playlists + Liked Songs.")

    # Apply filtering like a normal playlist
    if include_set:
        playlists = [p for p in playlists if slug(p["name"]) in include_set]
    if exclude_set:
        playlists = [p for p in playlists if slug(p["name"]) not in exclude_set]

    if not playlists:
        print("No playlists to process after filters.")
        return

    for p in playlists:
        pl_name = p["name"]
        pl_desc = p["description"]
        sp_pl_id = p["sp_id"]
        is_liked = p["is_liked"]

        print(f"\n=== Processing: {pl_name} ===")

        # Map/create YT playlist once
        if sp_pl_id in state["playlist_map"]:
            yt_playlist_id = state["playlist_map"][sp_pl_id]
        else:
            yt_playlist_id = ensure_playlist(ytm, pl_name, pl_desc)
            state["playlist_map"][sp_pl_id] = yt_playlist_id
            save_state(state)

        # Gather tracks
        if is_liked:
            tracks = fetch_liked_songs(sp)
        else:
            tracks = fetch_playlist_tracks(sp, sp_pl_id)

        print(f"{len(tracks)} tracks to process.")

        to_add: List[str] = []
        for t in tracks:
            key = t.sp_id  # per-track state keyed by Spotify track ID
            if key in state["track_map"]:
                vid = state["track_map"][key]
                if vid:
                    to_add.append(vid)
                continue

            vid = ytm_search_best_id(ytm, t)
            state["track_map"][key] = vid  # may be None if not found
            save_state(state)

            if vid:
                to_add.append(vid)
            else:
                print(f"  ! No good match for: {normalize_track(t.name, t.artists)}")

        if to_add:
            result = add_tracks_batched(ytm, yt_playlist_id, to_add)
            current_count = get_playlist_size(ytm, yt_playlist_id)

            print(f"Attempted: {result['attempted']}, added: {result['added']}, "
                  f"failed: {len(result['failed'])} to '{pl_name}'.")
            print(f"Playlist now shows {current_count} items on YT Music.")

            # Optional: dump failures to a small report so you can inspect later
            if result["failed"]:
                # Map each YT videoId we tried -> index in to_add (which aligns with tracks order)
                tried_map = {vid: idx for idx, vid in enumerate(to_add)}

                import csv
                with open("ytm_add_failures.csv", "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["videoId", "spotify_track", "reason"])
                    for vid, reason in result["failed"]:
                        idx = tried_map.get(vid)
                        if idx is not None and idx < len(tracks):
                            sp_track = normalize_track(tracks[idx].name, tracks[idx].artists)
                        else:
                            sp_track = ""
                        writer.writerow([vid, sp_track, reason])

                print("Wrote ytm_add_failures.csv with items YT Music rejected.")
        else:
            print("Nothing to add for this playlist.")

        print("\nDone 🎉  Rerun anytime; it resumes and only adds missing songs.")


if __name__ == "__main__":
    include = [s.strip() for s in os.getenv("INCLUDE_PLAYLISTS", "").split(",") if s.strip()]
    exclude = [s.strip() for s in os.getenv("EXCLUDE_PLAYLISTS", "").split(",") if s.strip()]
    transfer_playlists(include, exclude)
