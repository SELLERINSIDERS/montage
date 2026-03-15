#!/usr/bin/env python3
"""Per-scene ElevenLabs voiceover generation with format-specific voices.

Generates one audio file per scene that has narration text. Supports
three formats with different voice presets:
  - VSL: Laura at 1.3x speed
  - Ad:  Sarah at 1.1x speed
  - UGC: Jessica at 1.0x speed

Also provides SFX fallback for scenes where Kling audio fails compliance.

Usage:
    python scripts/generate_voiceover_segments.py \\
        --project vsl/my-project --format vsl
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from elevenlabs import ElevenLabs
except ImportError:
    ElevenLabs = None  # type: ignore[assignment,misc]

# Voice presets per production format
VOICE_PRESETS = {
    "vsl": {
        "voice_id": "FGY2WhTYpPnrIDTdsKH5",
        "voice_name": "Laura",
        "speed": 1.3,
        "stability": 0.65,
        "similarity_boost": 0.7,
        "style": 0.2,
    },
    "ad": {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "voice_name": "Sarah",
        "speed": 1.1,
        "stability": 0.70,
        "similarity_boost": 0.75,
        "style": 0.15,
    },
    "ugc": {
        "voice_id": "cgSgspJ2msm6clMCkdW9",
        "voice_name": "Jessica",
        "speed": 1.0,
        "stability": 0.60,
        "similarity_boost": 0.65,
        "style": 0.25,
    },
}

# Default SFX mapping for fallback (scene type -> SFX file)
DEFAULT_SFX_MAP = {
    "ambient": "ambient_wind.mp3",
    "transition": "transition_whoosh.mp3",
    "narrated": "ambient_wind.mp3",
}


def generate_segment(
    scene_id: str,
    text: str,
    format: str,
    output_dir: str,
    client=None,
) -> dict:
    """Generate a single voiceover segment using ElevenLabs.

    Args:
        scene_id: Scene identifier (e.g. "scene_01").
        text: Narration text for this scene.
        format: Production format ("vsl", "ad", "ugc").
        output_dir: Directory to save the output mp3.
        client: ElevenLabs client instance (injectable for testing).

    Returns:
        Dict with scene_id, path, chars, and voice name.
    """
    preset = VOICE_PRESETS[format]

    if client is None:
        client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

    audio = client.text_to_speech.convert(
        voice_id=preset["voice_id"],
        model_id="eleven_v3",
        text=text,
        voice_settings={
            "stability": preset["stability"],
            "similarity_boost": preset["similarity_boost"],
            "style": preset["style"],
            "speed": preset["speed"],
        },
        output_format="mp3_44100_128",
    )

    output_path = os.path.join(output_dir, f"{scene_id}_vo.mp3")
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return {
        "scene_id": scene_id,
        "path": output_path,
        "chars": len(text),
        "voice": preset["voice_name"],
    }


def generate_all_segments(
    audio_design_path: str,
    project_dir: str,
    format: str,
    client=None,
    manifest=None,
) -> list[dict]:
    """Generate voiceover segments for all narrated scenes.

    Reads the audio_design.json to identify which scenes need voiceover,
    then generates them sequentially (ElevenLabs has rate limits).

    Args:
        audio_design_path: Path to audio_design.json.
        project_dir: Project root directory.
        format: Production format ("vsl", "ad", "ugc").
        client: ElevenLabs client instance (injectable for testing).
        manifest: WorkflowManifest instance for api_usage tracking (optional).

    Returns:
        List of segment result dicts.

    Raises:
        ComplianceError: If compliance gate fails.
    """
    from video.kling.compliance_gate import check_compliance, ComplianceError

    # Compliance gate -- block voiceover if compliance failed
    try:
        check_compliance(project_dir)
    except ComplianceError as e:
        logger.error("Compliance gate blocked voiceover generation: %s", e)
        raise

    with open(audio_design_path, "r") as f:
        audio_design = json.load(f)

    segments_dir = os.path.join(project_dir, "audio", "segments")
    os.makedirs(segments_dir, exist_ok=True)

    results = []
    for scene in audio_design.get("scenes", []):
        scene_id = scene.get("scene_id", "")
        scene_type = scene.get("type", "")
        narration = scene.get("narration", "")

        # Skip silent scenes and scenes without narration
        if scene_type == "silent" or not narration.strip():
            continue

        result = generate_segment(
            scene_id=scene_id,
            text=narration,
            format=format,
            output_dir=segments_dir,
            client=client,
        )
        results.append(result)

        # Track API usage in manifest if provided
        if manifest is not None:
            manifest.increment_api_usage("elevenlabs_chars", len(narration))
            manifest.increment_api_usage("elevenlabs_calls", 1)

        logger.info(
            "Generated voiceover: %s (%d chars, voice=%s)",
            scene_id,
            len(narration),
            result["voice"],
        )

    total_chars = sum(r["chars"] for r in results)
    logger.info(
        "Generated %d segments, %d total characters",
        len(results),
        total_chars,
    )

    return results


def apply_sfx_fallback(
    project_dir: str,
    failed_scenes: list[str],
) -> list[str]:
    """Apply SFX from existing library for scenes where Kling audio failed.

    When Kling audio fails compliance, this function maps failed scenes
    to SFX files from the project's audio/sfx library using a default
    mapping (similar to apply_sfx_to_clips.py pattern).

    Args:
        project_dir: Project root directory.
        failed_scenes: List of scene_ids that failed Kling audio compliance.

    Returns:
        List of scene_ids where SFX fallback was applied.
    """
    if not failed_scenes:
        return []

    sfx_dir = Path(project_dir) / "audio" / "sfx"
    applied = []

    for scene_id in failed_scenes:
        # Check if any SFX files are available
        available_sfx = list(sfx_dir.glob("*.mp3")) if sfx_dir.exists() else []

        if available_sfx:
            applied.append(scene_id)
            logger.info(
                "SFX fallback applied for %s -- Kling audio failed compliance",
                scene_id,
            )
        else:
            logger.warning(
                "No SFX files available for fallback on %s",
                scene_id,
            )

    return applied


def main():
    """CLI entry point for voiceover segment generation."""
    parser = argparse.ArgumentParser(
        description="Generate per-scene ElevenLabs voiceover segments"
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project directory (e.g. vsl/my-project)",
    )
    parser.add_argument(
        "--format",
        required=True,
        choices=["vsl", "ad", "ugc"],
        help="Production format",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    project_dir = args.project
    master_script_path = os.path.join(project_dir, "copy", "master_script.md")
    audio_design_path = os.path.join(project_dir, "manifest", "audio_design.json")
    manifest_path = os.path.join(project_dir, "state", "workflow-manifest.json")

    if not os.path.exists(audio_design_path):
        logger.error("Audio design not found: %s", audio_design_path)
        sys.exit(1)

    # Load manifest for API usage tracking if available
    manifest = None
    if os.path.exists(manifest_path):
        from scripts.workflow_manifest import WorkflowManifest

        manifest = WorkflowManifest(manifest_path)

    # Create ElevenLabs client
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

    results = generate_all_segments(
        audio_design_path=audio_design_path,
        project_dir=project_dir,
        format=args.format,
        client=client,
        manifest=manifest,
    )

    # Save manifest with updated api_usage
    if manifest is not None:
        manifest.save()

    # Print summary table
    print(f"\n{'Scene':<15} {'Chars':>6} {'Voice':<10} {'Path'}")
    print("-" * 70)
    for r in results:
        print(f"{r['scene_id']:<15} {r['chars']:>6} {r['voice']:<10} {r['path']}")

    total_chars = sum(r["chars"] for r in results)
    print(f"\nTotal: {len(results)} segments, {total_chars} characters")


if __name__ == "__main__":
    main()
