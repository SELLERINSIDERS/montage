---
domain: video-production
updated: 2026-03-06
tags: [elevenlabs, whisper, heygen, voiceover, captions, avatar]
---

# Voiceover, Captions & Avatar

## ElevenLabs (Voiceover)
- **SDK**: `elevenlabs` v2.37.0, Key: `.env` → `ELEVENLABS_API_KEY`
- **Plan**: Starter ($5/mo, 30,000 credits). 192kbps needs Creator tier
- **ALWAYS use model `eleven_v3`** — latest, most natural, supports audio tags
- **NO SSML support in v3** — use `[pause]`, `[calm]`, `[deliberate]` etc. instead
- **Best voice for fast VSL**: Laura `FGY2WhTYpPnrIDTdsKH5` (enthusiast, American, fastest pace)
- **Speed 1.2 + 6 pauses max** = optimal for engaging VSL narration
- Voice speed varies by voice — Jessica/Hope are naturally slow even at high speed settings
- **Skill**: `.claude/skills/elevenlabs/SKILL.md`
- **Output**: `video/output/elevenlabs/`
- **Current**: Cleopatra VSL voiceover, V4 = Laura 1.2 speed, 3:25 duration

## HeyGen (Avatar)
- **Kate avatar**: `1c4f0c7552604526bf5f9a49822c3660`
- **Bella voice**: `628161fd1c79432d853b610e84dbc7a4`
- **Script**: `video/heygen/generate_avatar.py` — talking photo + Avatar IV motion
- **Output**: `video/output/heygen/`

## OpenAI Whisper (Captions)
- OpenAI Whisper API with auto audio extraction for files >25MB
- **Scripts**: `video/captions/transcribe.py`, `video/captions/transcribe_api.py`
- **Output**: `video/output/captions/` (JSON timestamps)
