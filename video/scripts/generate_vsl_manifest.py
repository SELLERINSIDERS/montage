#!/usr/bin/env python3
"""
Generate / update the VSL manifest from Whisper timestamps.

Usage:
  # Generate manifest from Whisper JSON (word-level timestamps)
  python generate_vsl_manifest.py --whisper path/to/whisper.json --voiceover voiceover.mp3

  # Adjust a single scene's trim points
  python generate_vsl_manifest.py --adjust scene_14a --trim-start 1.0 --trim-end 2.5

  # Show current manifest summary
  python generate_vsl_manifest.py --summary
"""

import json
import argparse
import os
import re
import sys

MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "remotion-video", "public", "vsl_manifest.json"
)

# Scene-to-script mapping: first few words of each scene's script line
# Used to find Whisper timestamps for each scene boundary
SCENE_SCRIPT_ANCHORS = [
    ("scene_01", "In 40 BC Cleopatra convinced"),
    ("scene_02", "Not for gold"),
    ("scene_03", "For access to one single mineral"),
    ("scene_04", "Cleopatra was crowned queen"),
    ("scene_05", "Surrounded by enemies"),
    ("scene_06", "Twice"),
    ("scene_07", "But she didn't just survive"),
    ("scene_08", "She discovered something"),
    ("scene_09", "On the shores of a dead lake"),
    ("scene_10", "A mineral so valuable"),
    ("scene_11", "She convinced Mark Antony"),
    ("scene_12", "Built factories along"),
    ("scene_13", "Leased the mineral rights"),
    ("scene_14a", "Ruled Egypt"),
    ("scene_14b", "Commanded navies"),
    ("scene_14c", "Spoke nine languages"),
    ("scene_14d", "Outlasted three Roman"),
    ("scene_15", "And every single night"),
    ("scene_16", "The most powerful woman"),
    ("scene_17", "But here's what history"),
    ("scene_18", "That mineral was magnesium"),
    ("scene_19", "The Dead Sea contains 30"),
    ("scene_20", "For 3 000 years"),
    ("scene_21a", "Through water"),
    ("scene_21b", "Through soil"),
    ("scene_21c", "Through food"),
    ("scene_22", "Then modern agriculture"),
    ("scene_23", "Industrial farming stripped"),
    ("scene_24", "Water treatment plants"),
    ("scene_25", "Processed food destroyed"),
    ("scene_26", "In just two generations"),
    ("scene_27", "Today studies show"),
    ("scene_28", "Your body uses it"),
    ("scene_29a", "Lying awake at 2"),
    ("scene_29b", "Racing thoughts"),
    ("scene_29c", "Waking up more tired"),
    ("scene_30", "It's not stress"),
    ("scene_31", "Cleopatra didn't have that problem"),
    ("scene_32", "And now for the first time"),
    ("scene_33", "Dead Sea magnesium"),
    ("scene_34", "But Evil Lance goes further"),
    ("scene_35a", "Combined with saffron"),
    ("scene_35b", "And L theanine"),
    ("scene_36", "Third party tested"),
    ("scene_37a", "Calm Not groggy"),
    ("scene_37b", "You drift off naturally"),
    ("scene_38", "Cleopatra built an empire"),
    ("scene_39", "Most people can't even"),
    ("scene_40", "The difference isn't willpower"),
    ("scene_41", "Right now Evil Lance"),
    ("scene_42", "Try it for 90 nights"),
]

CLIP_DURATION = 5.04  # seconds, from ffprobe


def calculate_trim(scene_duration: float, clip_duration: float = CLIP_DURATION) -> tuple:
    """Calculate optimal trim points based on scene duration.

    Strategy:
    - Short scenes (≤ 2.5s): center within the "safe middle" (1.5s to 4.0s)
    - Medium scenes (≤ 4.5s): center in full clip with small margins
    - Long scenes (> 4.5s): use full clip
    """
    if scene_duration <= 2.5:
        # Center in safe window (1.5 to 4.0)
        center = 2.75
        trim_start = max(0, center - scene_duration / 2)
        trim_end = trim_start + scene_duration
    elif scene_duration <= 4.5:
        # Center in full clip
        center = clip_duration / 2
        trim_start = max(0, center - scene_duration / 2)
        trim_end = min(clip_duration, trim_start + scene_duration)
    else:
        # Use full clip
        trim_start = 0
        trim_end = clip_duration

    return round(trim_start, 3), round(trim_end, 3)


def find_word_timestamp(words: list, anchor_text: str, after_ts: float = 0) -> float | None:
    """Find the start timestamp of an anchor phrase in whisper words.

    Args:
        after_ts: Only match occurrences starting after this timestamp (seconds).
                  Ensures sequential matching when phrases repeat in the script.
    """
    anchor_words = re.sub(r'[^\w\s]', '', anchor_text.lower()).split()
    if not anchor_words:
        return None

    for i in range(len(words) - len(anchor_words) + 1):
        # Skip words before the required timestamp
        word_ts = words[i].get("startMs", words[i].get("start", 0))
        if word_ts < 1000:
            word_ts_s = word_ts
        else:
            word_ts_s = word_ts / 1000.0
        if word_ts_s < after_ts:
            continue

        match = True
        for j, aw in enumerate(anchor_words):
            word_text = re.sub(r'[^\w]', '', words[i + j].get("text", "").lower())
            # Allow partial match (first 4 chars) for flexibility
            if not word_text.startswith(aw[:4]):
                match = False
                break
        if match:
            return words[i].get("startMs", words[i].get("start", 0))
    return None


def generate_from_whisper(whisper_path: str, voiceover_file: str | None = None):
    """Generate manifest from Whisper word-level timestamps."""
    with open(whisper_path) as f:
        whisper_data = json.load(f)

    # Handle both Whisper formats: {words: [...]} or [{text, startMs, endMs}, ...]
    if isinstance(whisper_data, list):
        words = whisper_data
    elif "words" in whisper_data:
        words = whisper_data["words"]
    elif "segments" in whisper_data:
        # Flatten segments into words
        words = []
        for seg in whisper_data["segments"]:
            if "words" in seg:
                words.extend(seg["words"])
    else:
        print("Error: Unrecognized Whisper JSON format", file=sys.stderr)
        sys.exit(1)

    # Normalize timestamp keys (support both start/startMs)
    for w in words:
        if "startMs" not in w and "start" in w:
            w["startMs"] = w["start"] * 1000 if w["start"] < 1000 else w["start"]
        if "endMs" not in w and "end" in w:
            w["endMs"] = w["end"] * 1000 if w["end"] < 1000 else w["end"]

    # Load existing manifest for scene metadata
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    # Find timestamps for each scene boundary (sequential matching)
    scene_starts = {}
    last_ts = 0  # Track last matched timestamp to ensure sequential order
    for scene_id, anchor in SCENE_SCRIPT_ANCHORS:
        ts = find_word_timestamp(words, anchor, after_ts=last_ts)
        if ts is not None:
            ts_s = ts / 1000.0 if ts > 1000 else ts  # Convert ms to seconds
            scene_starts[scene_id] = ts_s
            last_ts = ts_s  # Next anchor must be after this one
        else:
            print(f"  Warning: Could not find anchor for {scene_id}: '{anchor}'")

    # Calculate durations from consecutive scene starts
    scene_ids = [s[0] for s in SCENE_SCRIPT_ANCHORS]
    total_audio_duration = max(w.get("endMs", 0) for w in words) / 1000.0

    for i, scene in enumerate(manifest["scenes"]):
        sid = scene["id"]
        if sid not in scene_starts:
            print(f"  Keeping existing timing for {sid}")
            continue

        start = scene_starts[sid]

        # Find next scene's start for duration calculation
        if i + 1 < len(manifest["scenes"]):
            next_sid = manifest["scenes"][i + 1]["id"]
            end = scene_starts.get(next_sid, start + scene["duration_s"])
        else:
            end = total_audio_duration

        duration = round(end - start, 3)
        trim_start, trim_end = calculate_trim(duration)

        scene["duration_s"] = duration
        scene["trim_start_s"] = trim_start
        scene["trim_end_s"] = trim_end

    # Update voiceover
    if voiceover_file:
        manifest["meta"]["voiceover"] = voiceover_file
        manifest["meta"]["sfx_volume_scale"] = 0.4

    manifest["meta"]["generated_by"] = "generate_vsl_manifest.py"

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    total_dur = sum(s["duration_s"] for s in manifest["scenes"])
    print(f"\nManifest updated: {len(manifest['scenes'])} scenes, {total_dur:.1f}s total")
    if voiceover_file:
        print(f"Voiceover: {voiceover_file}")


def adjust_scene(scene_id: str, trim_start: float | None, trim_end: float | None):
    """Adjust trim points for a single scene."""
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    for scene in manifest["scenes"]:
        if scene["id"] == scene_id:
            if trim_start is not None:
                scene["trim_start_s"] = trim_start
            if trim_end is not None:
                scene["trim_end_s"] = trim_end
            print(f"Updated {scene_id}: trim {scene['trim_start_s']}s - {scene['trim_end_s']}s")
            break
    else:
        print(f"Error: Scene '{scene_id}' not found", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def show_summary():
    """Print manifest summary."""
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    total_dur = 0
    print(f"\n{'Scene':<12} {'Duration':>8} {'Trim':>14} {'Script Line':<60}")
    print("-" * 96)
    for scene in manifest["scenes"]:
        dur = scene["duration_s"]
        total_dur += dur
        trim = f"{scene['trim_start_s']:.1f}-{scene['trim_end_s']:.1f}s"
        line = scene["script_line"][:57] + "..." if len(scene["script_line"]) > 60 else scene["script_line"]
        print(f"{scene['id']:<12} {dur:>7.2f}s {trim:>14} {line:<60}")

    print("-" * 96)
    print(f"{'TOTAL':<12} {total_dur:>7.1f}s  ({total_dur/60:.1f} min)")

    vo = manifest["meta"].get("voiceover")
    print(f"\nVoiceover: {vo or 'NOT SET'}")
    print(f"SFX scale:  {manifest['meta'].get('sfx_volume_scale', 1.0)}")
    print(f"Generated:  {manifest['meta'].get('generated_by', 'unknown')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate/update VSL manifest")
    parser.add_argument("--whisper", help="Path to Whisper JSON with word-level timestamps")
    parser.add_argument("--voiceover", help="Voiceover filename (relative to public/)")
    parser.add_argument("--adjust", help="Scene ID to adjust trim points")
    parser.add_argument("--trim-start", type=float, help="New trim start in seconds")
    parser.add_argument("--trim-end", type=float, help="New trim end in seconds")
    parser.add_argument("--summary", action="store_true", help="Show manifest summary")

    args = parser.parse_args()

    if args.summary:
        show_summary()
    elif args.adjust:
        adjust_scene(args.adjust, args.trim_start, args.trim_end)
    elif args.whisper:
        generate_from_whisper(args.whisper, args.voiceover)
    else:
        # Default: show summary
        show_summary()
