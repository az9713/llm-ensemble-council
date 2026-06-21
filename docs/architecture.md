# Project: voice-notes-app — architecture constraints

- Target: real-time voice notes with live transcription and cross-device sync.
- Hard constraint: end-to-end latency under 300ms for transcription display.
- Team is 3 engineers; must avoid heavy ops burden. Prefer managed services.
- Budget: cost-sensitive; avoid always-on GPU inference where possible.
- Compliance: audio may contain PII; storage must be encryption-at-rest.
