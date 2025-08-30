# Spotify → YouTube Music Transfer

A Python tool to migrate your Spotify playlists — including **Liked Songs** — to YouTube Music.

- Reads all or selected playlists from Spotify
- Creates/updates matching playlists on YouTube Music
- Matches by **title + artists + duration**, prefers “song” results
- **Resumable & idempotent** with a state cache
- Post-add **healing pass**: re-searches alternatives for missing/duped items
- **Compare mode** to diff same-named playlists across Spotify and YTM
- CSV reports for failures and diffs

... (truncated for brevity in this cell, full content provided earlier) ...
