"""Kling audio compliance test runner for SC-5 verification.

Generates 10 test clips covering dialogue, ambient, and silent types,
evaluates each against a 5-point quality checklist, persists results,
and updates the workflow manifest compliance fields.

Usage:
    python -m scripts.kling_audio_compliance \
        --manifest-path state/workflow-manifest.json \
        --image-path test_image.png \
        --output-dir compliance_test_clips/

    # Evaluate only (skip generation):
    python -m scripts.kling_audio_compliance \
        --manifest-path state/workflow-manifest.json \
        --image-path test_image.png \
        --output-dir compliance_test_clips/ \
        --evaluate-only
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 5-point compliance checklist
# ---------------------------------------------------------------------------
CHECKLIST = {
    "no_artifacts": "Audio is free of clicks, pops, hiss, or digital artifacts",
    "matches_visual": "Audio content matches the visual action on screen",
    "dialogue_intelligible": "Any dialogue or narration is clearly understandable",
    "volume_appropriate": "Volume levels are consistent and appropriate for the scene",
    "no_abrupt_cuts": "No sudden audio starts/stops or jarring transitions",
}

# ---------------------------------------------------------------------------
# 10 compliance test scene prompts
# ---------------------------------------------------------------------------
COMPLIANCE_PROMPTS = [
    # Dialogue scenes (3)
    {
        "scene_id": "compliance_01",
        "type": "dialogue",
        "prompt": "A woman speaks directly to camera in a warmly lit room, explaining the benefits of natural sleep",
        "dialogue_text": "I finally found something that actually helps me unwind at night",
    },
    {
        "scene_id": "compliance_02",
        "type": "dialogue",
        "prompt": "A man sits at a desk, speaking to camera about his evening routine",
        "dialogue_text": "Every evening I take my supplement and within thirty minutes I feel calm",
    },
    {
        "scene_id": "compliance_03",
        "type": "dialogue",
        "prompt": "An expert in a lab coat explains ingredients while holding a supplement bottle",
        "dialogue_text": "Saffron has been studied for centuries for its calming properties",
    },
    # Ambient scenes (5)
    {
        "scene_id": "compliance_04",
        "type": "ambient",
        "prompt": "Golden sunrise over ancient Egyptian pyramids with sand dunes in foreground",
        "audio_prompt": "Desert wind, distant birds, soft ambient tones",
    },
    {
        "scene_id": "compliance_05",
        "type": "ambient",
        "prompt": "Close-up of saffron flowers blooming in a sun-drenched field",
        "audio_prompt": "Gentle breeze through flowers, soft nature sounds",
    },
    {
        "scene_id": "compliance_06",
        "type": "ambient",
        "prompt": "A serene bedroom at night with moonlight streaming through curtains",
        "audio_prompt": "Quiet nighttime ambience, crickets, soft wind",
    },
    {
        "scene_id": "compliance_07",
        "type": "ambient",
        "prompt": "Flowing water in a peaceful garden fountain surrounded by greenery",
        "audio_prompt": "Water flowing, gentle splashing, bird songs",
    },
    {
        "scene_id": "compliance_08",
        "type": "ambient",
        "prompt": "Steam rising from a warm cup of herbal tea on a wooden table",
        "audio_prompt": "Quiet indoor ambience, subtle steam sounds",
    },
    # Silent scenes (2)
    {
        "scene_id": "compliance_09",
        "type": "silent",
        "prompt": "Product bottle rotating slowly against a clean white background",
    },
    {
        "scene_id": "compliance_10",
        "type": "silent",
        "prompt": "Text overlay with supplement facts appearing on a dark gradient background",
    },
]


def generate_test_clips(client, image_path: str, output_dir: str) -> list[dict]:
    """Generate 10 test clips using KlingClient for compliance evaluation.

    Args:
        client: KlingClient instance (real API calls).
        image_path: Path to test image for all clips.
        output_dir: Directory to save generated clips.

    Returns:
        List of dicts with scene_id, type, clip_path, status.
    """
    os.makedirs(output_dir, exist_ok=True)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    results = []
    for scene in COMPLIANCE_PROMPTS:
        scene_id = scene["scene_id"]
        scene_type = scene["type"]
        output_path = os.path.join(output_dir, f"{scene_id}.mp4")

        prompt = scene["prompt"]
        enable_audio = scene_type != "silent"

        # For ambient scenes, append audio context to prompt
        if scene_type == "ambient" and scene.get("audio_prompt"):
            prompt = client._build_prompt(prompt, scene["audio_prompt"])

        try:
            logger.info("Generating clip %s (%s)...", scene_id, scene_type)
            client.image_to_video(
                image_bytes=image_bytes,
                prompt=prompt,
                output_path=output_path,
                enable_audio=enable_audio,
            )
            results.append({
                "scene_id": scene_id,
                "type": scene_type,
                "clip_path": output_path,
                "status": "generated",
            })
        except Exception as e:
            logger.error("Failed to generate clip %s: %s", scene_id, e)
            results.append({
                "scene_id": scene_id,
                "type": scene_type,
                "clip_path": None,
                "status": f"error: {e}",
            })

    return results


def evaluate_clip(scene: dict) -> dict:
    """Evaluate a single clip against the 5-point checklist.

    Args:
        scene: Dict containing scene_id and the 5 checklist booleans.

    Returns:
        Dict with scene_id, checks (dict of 5 booleans), and passed (bool).
    """
    checks = {key: bool(scene.get(key, False)) for key in CHECKLIST}
    return {
        "scene_id": scene["scene_id"],
        "checks": checks,
        "passed": all(checks.values()),
    }


def generate_compliance_report(evaluations: list[dict]) -> dict:
    """Aggregate clip evaluations into an overall compliance report.

    Args:
        evaluations: List of evaluate_clip() results.

    Returns:
        Dict with overall_status, passed_count, failed_count, clips, evaluated_at.
    """
    passed_count = sum(1 for e in evaluations if e["passed"])
    failed_count = len(evaluations) - passed_count
    overall_status = "passed" if failed_count == 0 else "failed"

    return {
        "overall_status": overall_status,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "clips": evaluations,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_compliance_result(
    report: dict, config_path: str = "config/kling_audio_compliance.json"
) -> None:
    """Write compliance report to config file with history tracking.

    If the file exists, appends to the history array and updates the latest key.

    Args:
        report: Compliance report from generate_compliance_report().
        config_path: Path to the JSON config file.
    """
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            data = json.load(f)
    else:
        data = {"latest": None, "history": []}

    data["latest"] = report
    data["history"].append(report)

    os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


def update_manifest_compliance(
    manifest_path: str, status: str, date: str
) -> None:
    """Update workflow manifest with compliance status and date.

    Args:
        manifest_path: Path to workflow-manifest.json.
        status: "passed" or "failed".
        date: ISO timestamp of evaluation.
    """
    from scripts.workflow_manifest import WorkflowManifest

    manifest = WorkflowManifest(manifest_path)
    manifest.data["audio_config"]["kling_compliance_status"] = status
    manifest.data["audio_config"]["kling_compliance_date"] = date
    manifest.save()


def _interactive_checklist(scene_id: str, clip_path: str) -> dict:
    """Present interactive checklist for a single clip.

    Args:
        scene_id: Identifier for the clip.
        clip_path: Path to the video file.

    Returns:
        Dict with scene_id and 5 checklist booleans.
    """
    print(f"\n--- Evaluating {scene_id} ---")
    print(f"Clip: {clip_path}")
    print("Review the clip and answer each question (y/n):\n")

    result = {"scene_id": scene_id}
    for key, description in CHECKLIST.items():
        while True:
            answer = input(f"  {description}? [y/n]: ").strip().lower()
            if answer in ("y", "n"):
                result[key] = answer == "y"
                break
            print("  Please enter 'y' or 'n'")

    return result


def main():
    """CLI entrypoint for Kling audio compliance evaluation."""
    parser = argparse.ArgumentParser(
        description="Kling audio compliance test runner"
    )
    parser.add_argument(
        "--manifest-path",
        required=True,
        help="Path to workflow-manifest.json",
    )
    parser.add_argument(
        "--image-path",
        required=True,
        help="Test image to use for all 10 clips",
    )
    parser.add_argument(
        "--output-dir",
        default="compliance_test_clips/",
        help="Directory to save generated clips (default: compliance_test_clips/)",
    )
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="Skip generation, evaluate existing clips in output-dir",
    )
    args = parser.parse_args()

    # Generate clips (unless --evaluate-only)
    if not args.evaluate_only:
        from video.kling.api_client import KlingClient

        client = KlingClient()
        print("Generating 10 compliance test clips...")
        clips = generate_test_clips(client, args.image_path, args.output_dir)
        failed_gen = [c for c in clips if c["status"] != "generated"]
        if failed_gen:
            print(f"\nWARNING: {len(failed_gen)} clips failed to generate:")
            for c in failed_gen:
                print(f"  {c['scene_id']}: {c['status']}")
            print()

    # Interactive evaluation
    print("\n=== Compliance Evaluation ===")
    print(f"Checklist ({len(CHECKLIST)} points):")
    for key, desc in CHECKLIST.items():
        print(f"  - {desc}")
    print()

    evaluations = []
    for scene in COMPLIANCE_PROMPTS:
        scene_id = scene["scene_id"]
        clip_path = os.path.join(args.output_dir, f"{scene_id}.mp4")
        if not os.path.exists(clip_path):
            print(f"SKIP {scene_id}: clip not found at {clip_path}")
            continue
        answers = _interactive_checklist(scene_id, clip_path)
        evaluation = evaluate_clip(answers)
        evaluations.append(evaluation)
        status = "PASS" if evaluation["passed"] else "FAIL"
        print(f"  Result: {status}")

    if not evaluations:
        print("No clips evaluated. Exiting.")
        sys.exit(1)

    # Generate and save report
    report = generate_compliance_report(evaluations)
    config_path = "config/kling_audio_compliance.json"
    save_compliance_result(report, config_path)
    print(f"\nReport saved to {config_path}")

    # Update manifest
    update_manifest_compliance(
        args.manifest_path,
        report["overall_status"],
        report["evaluated_at"],
    )
    print(f"Manifest updated: kling_compliance_status={report['overall_status']}")

    # Summary
    print(f"\n=== OVERALL: {report['overall_status'].upper()} ===")
    print(f"Passed: {report['passed_count']}/{len(evaluations)}")
    if report["failed_count"] > 0:
        failed = [c for c in evaluations if not c["passed"]]
        print("Failed clips:")
        for c in failed:
            print(f"  {c['scene_id']}: {c['checks']}")


if __name__ == "__main__":
    main()
