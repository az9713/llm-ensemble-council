# Project: voice-notes-app — data & storage notes

- Expected scale: 50k users year one, ~5 notes/user/day, avg 2 minutes audio.
- Sync requires conflict resolution; offline edits must merge deterministically.
- Prior decision (recorded): store transcripts separately from raw audio blobs.
- Postgres is already used for user accounts; ops familiarity is high.
- Object storage (S3-compatible) is the cheapest fit for audio blobs.
