"""EDL (Edit Decision List) generator for Remotion post-production.

Reads workflow manifest + audio_design.json + Whisper JSON to produce
an EDL JSON file that drives the UniversalComposition in Remotion.

Usage:
    from scripts.edl_generator import generate_edl, modify_edl

    edl = generate_edl(
        manifest_path="vsl/nightcap/state/manifest.json",
        audio_design_path="vsl/nightcap/state/audio_design.json",
        whisper_path="vsl/nightcap/audio/whisper.json",
    )
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Format dimensions: (width, height)
FORMAT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "vsl": (1080, 1920),
    "ad": (1080, 1920),
    "ugc": (1080, 1080),
}

# Minimum playback rate before clamping
MIN_PLAYBACK_RATE = 0.5

# Default values
DEFAULT_FPS = 24
DEFAULT_CAPTION_PRESET = "tiktok_bold"
DEFAULT_PLATFORM_TARGET = "generic"
DEFAULT_RENDER_QUALITY = "preview"


def _load_json(path: str, label: str = "file") -> dict:
    """Load a JSON file with a descriptive error on failure."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    with open(p, "r") as f:
        return json.load(f)


def _derive_scene_durations(
    whisper_data: dict, scene_ids: list[str]
) -> dict[str, float]:
    """Derive per-scene durations from Whisper segment start/end times.

    Groups segments by scene_id, uses min(start) to max(end) per scene.
    """
    scene_times: dict[str, list[tuple[float, float]]] = {}
    for seg in whisper_data.get("segments", []):
        sid = seg.get("scene_id")
        if sid and sid in scene_ids:
            scene_times.setdefault(sid, []).append(
                (seg["start"], seg["end"])
            )

    durations: dict[str, float] = {}
    for sid in scene_ids:
        times = scene_times.get(sid, [])
        if times:
            start = min(t[0] for t in times)
            end = max(t[1] for t in times)
            durations[sid] = round(end - start, 3)
        else:
            # Scene has no whisper segments — use default
            durations[sid] = 5.0
            logger.warning(
                "No Whisper segments for %s, using default 5.0s duration", sid
            )
    return durations


def _build_scene_entry(
    scene: dict,
    audio_design_scenes: dict,
    duration_s: float,
    clip_duration_s: Optional[float] = None,
) -> dict:
    """Build a single EDL scene entry from manifest + audio_design data."""
    scene_id = scene["scene_id"]
    audio_info = audio_design_scenes.get(scene_id, {})
    classification = audio_info.get("classification", "voiceover_only")

    # Map ambient audio from audio_design
    ambient_audio = []
    for amb in audio_info.get("ambient_audio", []):
        ambient_audio.append({
            "src": amb["src"],
            "volume": amb.get("volume", 0.3),
            "loop": amb.get("loop", True),
            "fade_in": amb.get("fade_in", False),
            "delay_s": amb.get("delay_s", 0),
        })

    # Build clip source path
    clip_src = scene.get("video", f"video/clips/{scene_id}.mp4")

    # Check if playback rate clamping needed
    playback_rate_override = None
    if clip_duration_s and clip_duration_s > 0 and duration_s > 0:
        rate = clip_duration_s / duration_s
        if rate < MIN_PLAYBACK_RATE:
            playback_rate_override = MIN_PLAYBACK_RATE
            logger.warning(
                "Scene %s: playback rate %.2f clamped to %.1f "
                "(clip=%.1fs, scene=%.1fs)",
                scene_id,
                rate,
                MIN_PLAYBACK_RATE,
                clip_duration_s,
                duration_s,
            )

    entry = {
        "id": scene_id,
        "clip_src": clip_src,
        "duration_s": duration_s,
        "trim_start_s": 0,
        "trim_end_s": duration_s,
        "audio_type": classification,
        "ambient_audio": ambient_audio,
        "transition_in": "hard_cut",
        "label": scene_id.replace("_", " ").title(),
        "playback_rate_override": playback_rate_override,
    }
    return entry


def generate_edl(
    manifest_path: str,
    audio_design_path: str,
    whisper_path: str,
    format_overrides: Optional[dict] = None,
) -> dict:
    """Generate an EDL JSON from manifest + audio_design + whisper data.

    Args:
        manifest_path: Path to workflow manifest JSON.
        audio_design_path: Path to audio_design.json with per-scene classification.
        whisper_path: Path to Whisper JSON with segment timing.
        format_overrides: Optional dict to override format, caption_preset, etc.

    Returns:
        EDL dictionary matching the TypeScript edlSchema.

    Raises:
        FileNotFoundError: If whisper_path does not exist.
    """
    # Load inputs
    manifest = _load_json(manifest_path, "Manifest")
    audio_design = _load_json(audio_design_path, "Audio design")
    whisper_data = _load_json(whisper_path, "Whisper data")

    fmt = manifest.get("format", "vsl")
    slug = manifest.get("slug", "untitled")

    # Get approved scenes from manifest
    approved_scenes = []
    for scene in manifest.get("scenes", []):
        gate = scene.get("gates", {}).get("video", {})
        if gate.get("status") == "approved":
            approved_scenes.append(scene)

    if not approved_scenes:
        logger.warning("No approved scenes found in manifest")

    # Derive scene durations from whisper data
    scene_ids = [s["scene_id"] for s in approved_scenes]
    scene_durations = _derive_scene_durations(whisper_data, scene_ids)

    # Audio design scene data
    audio_design_scenes = audio_design.get("scenes", {})

    # Build scene entries
    scenes = []
    for scene in approved_scenes:
        sid = scene["scene_id"]
        duration = scene_durations.get(sid, 5.0)
        entry = _build_scene_entry(scene, audio_design_scenes, duration)
        scenes.append(entry)

    # Format dimensions
    overrides = format_overrides or {}
    effective_format = overrides.get("format", fmt)
    width, height = FORMAT_DIMENSIONS.get(effective_format, (1080, 1920))

    # Build voiceover section
    voiceover = {
        "src": "audio/voiceover.mp3",
        "volume": 1.0,
        "whisper_data": "audio/whisper.json",
    }

    # Build EDL
    now = datetime.now(timezone.utc).isoformat()
    edl = {
        "meta": {
            "fps": overrides.get("fps", DEFAULT_FPS),
            "width": overrides.get("width", width),
            "height": overrides.get("height", height),
            "title": overrides.get("title", slug),
            "format": effective_format,
            "caption_preset": overrides.get(
                "caption_preset", DEFAULT_CAPTION_PRESET
            ),
            "platform_target": overrides.get(
                "platform_target", DEFAULT_PLATFORM_TARGET
            ),
            "render_quality": overrides.get(
                "render_quality", DEFAULT_RENDER_QUALITY
            ),
            "version": 1,
        },
        "voiceover": voiceover,
        "scenes": scenes,
        "intro": None,
        "outro": None,
        "changelog": [
            {
                "version": 1,
                "date": now,
                "changes": [
                    f"Initial EDL generated from manifest with {len(scenes)} scenes"
                ],
            }
        ],
    }

    return edl


def modify_edl(edl_path: str, changes: list[dict]) -> dict:
    """Apply modifications to an existing EDL, bump version, update changelog.

    Args:
        edl_path: Path to existing edl.json.
        changes: List of change dicts, each with 'type' and type-specific fields.
            Supported types:
            - update_label: {scene_id, label}
            - reorder: {scene_order: [scene_id, ...]}
            - update_duration: {scene_id, duration_s}

    Returns:
        Modified EDL dictionary.
    """
    edl = _load_json(edl_path, "EDL")

    change_descriptions = []

    for change in changes:
        change_type = change.get("type")

        if change_type == "update_label":
            scene_id = change["scene_id"]
            new_label = change["label"]
            for scene in edl["scenes"]:
                if scene["id"] == scene_id:
                    scene["label"] = new_label
                    change_descriptions.append(
                        f"Updated label for {scene_id}: {new_label}"
                    )
                    break

        elif change_type == "reorder":
            order = change["scene_order"]
            scene_map = {s["id"]: s for s in edl["scenes"]}
            edl["scenes"] = [scene_map[sid] for sid in order if sid in scene_map]
            change_descriptions.append(
                f"Reordered scenes: {', '.join(order)}"
            )

        elif change_type == "update_duration":
            scene_id = change["scene_id"]
            new_duration = change["duration_s"]
            for scene in edl["scenes"]:
                if scene["id"] == scene_id:
                    scene["duration_s"] = new_duration
                    scene["trim_end_s"] = new_duration
                    change_descriptions.append(
                        f"Updated duration for {scene_id}: {new_duration}s"
                    )
                    break

        else:
            change_descriptions.append(f"Unknown change type: {change_type}")

    # Bump version
    edl["meta"]["version"] = edl["meta"].get("version", 1) + 1

    # Append changelog
    now = datetime.now(timezone.utc).isoformat()
    edl.setdefault("changelog", []).append({
        "version": edl["meta"]["version"],
        "date": now,
        "changes": change_descriptions or ["Modification applied"],
    })

    # Write back
    with open(edl_path, "w") as f:
        json.dump(edl, f, indent=2)

    return edl
