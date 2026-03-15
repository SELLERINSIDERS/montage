# Montage

**End-to-end AI video production pipeline — from script to final render.**

Montage is an open-source framework that orchestrates the entire video production workflow using AI agents. Write a script, generate images, synthesize video clips, add voiceover and sound design, and render the final cut — all through an automated pipeline with human review gates.

Built for **VSLs** (3–6 min), **short ads** (15–60s), and **UGC clips** (15–30s).

---

## What It Does

```
Script → Compliance → Scene Design → Camera Plan → Images → Video → Voiceover → Sound Design → Post-Production → Final Render
```

Each stage is handled by a specialized AI agent. You review and approve at quality gates. The pipeline resumes from where it left off if interrupted.

### Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Image Generation** | Gemini 3.1 Flash (Nano Banana Pro) | 2K scene storyboards from text prompts |
| **Video Synthesis** | Kling V3 (via UseAPI.net proxy) | Image-to-video with embedded audio |
| **Voiceover** | ElevenLabs | Text-to-speech narration |
| **Transcription** | OpenAI Whisper | Voiceover timing and captions |
| **Avatar Video** | HeyGen | Talking-head avatar generation (optional) |
| **Post-Production** | Remotion 4.0 | Final composition — clips + voiceover + SFX + captions |
| **Dashboard** | Next.js 16 + React 19 + Supabase | Real-time production tracking and review UI |
| **Orchestration** | Python 3.11+ | Phase dispatch, gate enforcement, queue polling |
| **Database** | Supabase (PostgreSQL) | Productions, scenes, review decisions, job queue |
| **AI Agents** | Claude Code | Skill-based agents for each production phase |

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **FFmpeg** (`brew install ffmpeg` on macOS)
- **Claude Code** CLI (for AI agent orchestration)
- API keys for: Kling (via UseAPI.net), ElevenLabs, Google Gemini, OpenAI, and optionally HeyGen

### 1. Clone & Install

```bash
git clone https://github.com/SELLERINSIDERS/montage.git
cd montage

# Python
python3 -m venv .venv
source .venv/bin/activate
pip install google-genai requests python-dotenv

# Dashboard
cd dashboard && npm install && cd ..

# Remotion
cd video/remotion-video && npm install && cd ../..
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# Kling Video (UseAPI.net proxy — recommended)
USEAPI_KEY=your_useapi_bearer_token
KLING_USE_PROXY=true

# Kling Direct API (fallback — no audio support)
KLING_ACCESS_KEY=your_kling_access_key
KLING_SECRET_KEY=your_kling_secret_key

# ElevenLabs (voiceover)
ELEVENLABS_API_KEY=your_elevenlabs_api_key

# Google Gemini (image generation)
GEMINI_API_KEY=your_google_gemini_api_key

# HeyGen (avatar video — optional)
HEYGEN_API_KEY=your_heygen_api_key

# OpenAI (Whisper transcription)
OPENAI_API_KEY=your_openai_api_key

# Supabase (dashboard + production tracking)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your_anon_key
```

### 3. Set Up Supabase

Create a [Supabase](https://supabase.com) project, then run the migrations in order:

```bash
# Using Supabase CLI
supabase db push

# Or manually — run each migration file against your database:
# supabase/migrations/001_initial_schema.sql
# supabase/migrations/002_schema_dashboard.sql
# ... through 008_auto_video_on_image_approval.sql
```

This creates the core tables: `productions`, `scenes`, `review_decisions`, `regeneration_queue`, `generation_events`, `prompt_versions`, and `production_videos`.

### 4. Start the Dashboard

```bash
# Option A: Start everything (dashboard + job poller)
./dev.sh

# Option B: Start separately
cd dashboard && npm run dev          # Dashboard on localhost:3000
python -m scripts.job_poller         # Regeneration queue daemon
```

### 5. Run Your First Production

Open Claude Code in the project directory and start a production:

```
/project:vsl-production
```

The orchestrator will ask you for:
- **Production type**: VSL, short ad, or UGC clip
- **Project slug**: e.g., `my-first-vsl`
- **Product brief**: What you're selling, key angles, target audience

It scaffolds the project folder and walks you through each phase.

---

## Production Pipeline

### Phases

| # | Phase | Agent | Output |
|---|-------|-------|--------|
| 1 | **Intake & Brief** | VSL Production Coordinator | `copy/brief.md` |
| 2 | **Research** | Research Agent | `copy/research.md` |
| 3 | **Script Writing** | Copywriter Agent | `copy/script.md`, `copy/script_narrated.md` |
| 4 | **Scene Design** | Cinematic Director | `prompts/scene_prompts.md` |
| 5 | **Camera Planning** | Cinematographer | `prompts/camera_plan.json` |
| 6 | **Compliance Gate** | Compliance Checker | Pass/Fail — blocks production on failure |
| 7 | **Expert Panel** | 10-Expert Panel | Score 90+ required to proceed |
| 8 | **Image Generation** | Nano Banana Pro (Gemini) | `images/v1/*.png` |
| 9 | **Image Revisions** | Director + Gemini | `images/final/*.png` (2K) |
| 10 | **Video Generation** | Kling V3 Agent | `video/clips/*.mp4` |
| 11 | **Voiceover** | ElevenLabs Agent | `audio/voiceover.mp3` + `audio/whisper.json` |
| 12 | **Sound Design** | Sound Designer | `manifest/audio_design.json` |
| 13 | **Post-Production** | Video Editor | EDL JSON for Remotion |
| 14 | **Audio Mix** | Audio Engineer | Final composition in Remotion |
| 15 | **Final Review** | Human (via Dashboard) | Approve or flag for revision |

### Quality Gates

Every production passes through two mandatory gates before entering visual production:

1. **FDA/FTC Compliance Check** — Scans scripts for banned claims (disease claims, drug claims, absolute claims, superiority claims). Configurable rules in `docs/knowledge/shared/compliance.md`.
2. **10-Expert Panel Review** — Simulated expert panel scores the script across 10 dimensions. Must average 90+ to proceed.

### Project Folder Structure

Every production lives in its own isolated folder:

```
vsl/my-first-vsl/
├── README.md                    # Status + current phase
├── copy/                        # Brief, research, scripts, compliance reports
├── prompts/                     # Scene prompts, camera plan
├── images/v1/ + final/          # Generated scene frames (1K and 2K)
├── audio/                       # Voiceover MP3 + Whisper transcription
├── video/clips/ + final/        # Kling clips + rendered output
├── manifest/                    # Generation manifests + audio design
└── state/                       # Workflow manifest + phase checkpoints
```

---

## Dashboard

The real-time dashboard lets you monitor productions, review assets, and control the pipeline:

- **Kanban board** — Drag-and-drop production cards across pipeline stages
- **Scene review** — Approve, flag, or request regeneration for individual scenes
- **Regeneration queue** — Flagged scenes automatically re-enter the generation pipeline with your feedback applied
- **Final review grid** — Side-by-side comparison of all scenes before final render
- **Real-time updates** — Supabase subscriptions push changes instantly

The dashboard reads from and writes to Supabase. The Python pipeline watches for review decisions and acts on them automatically.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code CLI                     │
│              (AI Agent Orchestration)                  │
│                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Script   │ │ Scene    │ │ Camera   │ │ Compliance│ │
│  │ Writer   │ │ Director │ │ Planner  │ │ Gate     │ │
│  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Python Orchestration Layer               │
│                                                       │
│  orchestrator.py ──► gate_runner.py                   │
│  manifest_sync.py    regenerate_scene.py              │
│  job_poller.py       prompt_rewriter.py               │
│  dashboard_sync.py   checkpoint.py                    │
└───────────────────────┬─────────────────────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
     ┌────────────┐ ┌────────┐ ┌────────────┐
     │ Kling V3   │ │ Gemini │ │ ElevenLabs │
     │ (Video)    │ │(Images)│ │ (Voice)    │
     └────────────┘ └────────┘ └────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                 Supabase (PostgreSQL)                  │
│                                                       │
│  productions ─── scenes ─── review_decisions          │
│  regeneration_queue ─── generation_events             │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│           Next.js Dashboard (localhost:3000)           │
│                                                       │
│  Kanban Board │ Scene Review │ Final Review Grid       │
│  Real-time Updates via Supabase Subscriptions         │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Remotion (Video Rendering)                │
│                                                       │
│  Clips + Voiceover + SFX + Captions → Final MP4      │
└─────────────────────────────────────────────────────┘
```

---

## Available Commands

These Claude Code skills are available in the project:

| Command | What It Does |
|---------|-------------|
| `/project:vsl-production` | Start or resume a full production |
| `/project:cinematic-director` | Design scenes with the Epic Scale Doctrine |
| `/project:cinematographer` | Generate and validate camera plans |
| `/project:nanobanana` | Generate images with Nano Banana Pro (Gemini) |
| `/project:kling-video-workflow` | Generate video clips with Kling V3 |
| `/project:sound-design` | Map SFX to scenes |
| `/project:remotion-audio` | Compose final audio mix in Remotion |
| `/project:video-editor` | Generate EDL for post-production |
| `/project:feedback-loop` | Capture and retrieve production feedback |
| `/project:video-prompting-guide` | Reference guide for video prompt writing |

---

## Key Scripts

### Orchestration

```bash
# Start the regeneration queue daemon
python -m scripts.job_poller --interval 10

# Sync workflow manifest from checkpoint files
python -m scripts.manifest_sync vsl/my-project

# Sync production state to dashboard
python -m scripts.dashboard_sync vsl/my-project
```

### Media Processing

```bash
# Apply SFX to all clips in a production
python scripts/apply_sfx_to_clips.py --project vsl/my-project

# Re-apply SFX to a single scene
python scripts/reapply_sfx_single.py --project vsl/my-project --scene scene_01

# Generate voiceover segments
python scripts/generate_voiceover_segments.py --project vsl/my-project --format vsl

# Transcribe voiceover with Whisper
python scripts/transcribe_segments.py --project vsl/my-project
```

### Post-Production

```bash
# Generate EDL for Remotion
python scripts/post_production.py vsl/my-project

# Render final video with Remotion
cd video/remotion-video
npx remotion render UniversalVSL --props='path/to/edl.json'
```

---

## Crash Recovery

Montage uses checkpoint-based crash recovery:

- Every phase writes checkpoint files to `{project}/state/`
- Handoff JSON files pass data between phases
- If the pipeline crashes, re-invoke `/project:vsl-production` — it reads the workflow manifest and resumes from the last incomplete phase
- The `job_poller` daemon uses optimistic locking to prevent duplicate work

---

## Configuration

### Kling Video Generation

Montage supports two modes for Kling:

| Mode | Proxy (UseAPI.net) | Direct API |
|------|-------------------|------------|
| Audio support | Yes (embedded in clips) | No |
| Image upload | CDN URL (auto-uploaded) | Raw base64 |
| Model | `kling-v3-omni` | `kling-v3` |
| Recommended | **Production** | Testing only |

Key settings (always applied):
- `cfg_scale: 0.4`
- Always include `negative_prompt`
- 10 MB image size limit

### Image Generation (Nano Banana Pro)

- Model: `gemini-3.1-flash-image-preview`
- **`MAX_WORKERS=1`** for 2K generation (concurrent requests deadlock)
- 3–4 min per image at 2K resolution
- 120s timeout, 5s rate limit delay, 3 retries

### SFX Library

56 approved + 13 banned sound effects in `video/remotion-video/public/sfx/`. Includes: ocean waves, wind, desert wind, birdsong, torch crackle, crowd murmur, temple echo, campfire, and more.

Volume hierarchy:
- Primary: 0.6–0.8
- Ambient: 0.3–0.5
- Detail: 0.15–0.3

No single sound effect may cover more than 20% of total scenes.

---

## Database Schema

Run the 8 migrations in `supabase/migrations/` to set up:

| Table | Purpose |
|-------|---------|
| `productions` | One row per VSL/ad/UGC — format, slug, phase, status, manifest |
| `scenes` | One row per scene — image/video/gate status, feedback, flags |
| `review_decisions` | Dashboard writes approvals and flags here |
| `regeneration_queue` | Flagged scenes queue for re-generation |
| `generation_events` | Activity feed for real-time dashboard |
| `prompt_versions` | Tracks prompt history and adjustments per scene |
| `production_videos` | Rendered video versions (preview/final) |

All tables have Row Level Security (RLS) policies. The dashboard uses Supabase real-time subscriptions for instant updates.

---

## Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run integration tests (requires API keys)
pytest -m integration
```

Test coverage includes: dashboard sync, EDL generation, compliance gates, Kling client, manifest resume, voiceover segments, SFX application, workflow manifest, and more.

---

## Project Structure

```
montage/
├── .claude/commands/           # 10 AI agent skill definitions
├── config/                     # API costs, rate limits, lessons learned
├── dashboard/                  # Next.js 16 real-time production dashboard
├── docs/knowledge/             # Framework documentation
│   ├── shared/                 #   Compliance, image gen, lessons learned
│   └── video/                  #   Kling, Remotion, voiceover, pipeline
├── scripts/                    # 40+ Python orchestration modules
├── supabase/migrations/        # 8 PostgreSQL migration files
├── tests/                      # pytest integration test suite
├── video/
│   ├── captions/               # Whisper transcription
│   ├── editing/                # Videographer utilities
│   ├── heygen/                 # Avatar video generation
│   ├── kling/                  # Kling V3 API client + batch generation
│   └── remotion-video/         # Remotion composition + rendering
├── .env.example                # API key template
├── dev.sh                      # Start dashboard + job poller
└── pyproject.toml              # Python project config
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit (`git commit -m 'Add my feature'`)
6. Push (`git push origin feature/my-feature`)
7. Open a Pull Request

---

## License

MIT

---

Built with Claude Code, Kling AI, Remotion, ElevenLabs, Google Gemini, and Supabase.
