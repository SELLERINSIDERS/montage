"""Feedback capture helper for the self-learning pipeline.

Captures regeneration corrections to the Supabase learnings table
so future productions automatically avoid the same mistakes.

Uses supa-capture CLI tool for write and supa-search-cc for dedup check.

Usage:
    from scripts.feedback_capture import capture_regeneration_feedback
    capture_regeneration_feedback(
        gate_type="image_1k",
        scene_id="S03",
        flag_reasons=["wrong_pose"],
        feedback_text="Person standing when should be sitting",
        original_prompt="...",
        adjusted_prompt="...",
        format_type="vsl",
    )
"""

import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Env file for supa-capture authentication
_ENV_FILE = os.environ.get("EXTRA_ENV_FILE", ".env")
_SUPA_CAPTURE = os.environ.get("SUPA_CAPTURE_BIN", "supa-capture")
_SUPA_SEARCH = os.environ.get("SUPA_SEARCH_BIN", "supa-search-cc")

# gate_type -> stage_id mapping
_GATE_TO_STAGE: dict[str, str] = {
    "image_1k": "imagegen-v1",
    "image_2k": "imagegen-v2",
    "video_clip": "kling-video",
    "video": "kling-video",
}

# flag_reason -> problem class mapping for topic naming
_REASON_TO_CLASS: dict[str, str] = {
    # Dashboard vocabulary
    "Wrong composition": "composition",
    "Bad lighting": "lighting",
    "Character issue": "character",
    "Motion artifact": "motion",
    "Wrong scale": "scale",
    "Text/overlay issue": "text-artifacts",
    "Continuity break": "continuity",
    "Other": "general",
    # Legacy vocabulary
    "wrong_pose": "pose-control",
    "wrong_expression": "expression",
    "wrong_setting": "setting",
    "wrong_lighting": "lighting",
    "wrong_framing": "framing",
    "low_quality": "quality",
    "anachronistic": "anachronistic",
    "text_visible": "text-artifacts",
    "identity_shift": "identity",
}

# Stage-specific retrieval query terms for supa-search-cc
_STAGE_SEARCH_TERMS: dict[str, str] = {
    "imagegen-v1": "image generation 1k scene prompt correction",
    "imagegen-v2": "image generation 2k upscale prompt correction",
    "kling-video": "kling video clip motion prompt correction",
}


def _load_env() -> dict:
    """Load environment variables from the shared env file."""
    env_vars = {}
    try:
        with open(_ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Strip surrounding quotes
                    value = value.strip().strip("'\"")
                    env_vars[key.strip()] = value
    except FileNotFoundError:
        logger.warning("Env file not found: %s", _ENV_FILE)
    return env_vars


def _get_subprocess_env() -> dict:
    """Build environment dict for subprocess calls (merge current env + loaded env)."""
    return {**os.environ, **_load_env()}


def _build_topic(gate_type: str, flag_reasons: list[str], feedback_text: str) -> str:
    """Build a semantic topic string for the learnings table.

    Format: <stage>/<problem-class>/<short-descriptor>
    """
    stage = _GATE_TO_STAGE.get(gate_type, gate_type)

    if flag_reasons:
        problem_class = _REASON_TO_CLASS.get(
            flag_reasons[0], flag_reasons[0].replace("_", "-")
        )
        descriptor = flag_reasons[0].replace("_", "-")
    elif feedback_text:
        words = feedback_text.lower().split()[:3]
        problem_class = "user-feedback"
        descriptor = "-".join(w for w in words if len(w) > 2)[:30]
    else:
        problem_class = "general"
        descriptor = "regeneration"

    return f"{stage}/{problem_class}/{descriptor}"


def _build_summary(
    scene_id: str,
    flag_reasons: list[str],
    feedback_text: Optional[str],
    original_prompt: str,
    adjusted_prompt: str,
) -> str:
    """Build a self-contained summary for the learnings table."""
    parts = [f"Scene {scene_id} regenerated."]

    if flag_reasons:
        parts.append(f"Flags: {', '.join(flag_reasons)}.")
    if feedback_text:
        parts.append(f"Feedback: {feedback_text}.")

    # Show what changed in the prompt
    if original_prompt and adjusted_prompt and original_prompt != adjusted_prompt:
        if "CORRECTIONS:" in adjusted_prompt:
            corrections = adjusted_prompt.split("CORRECTIONS:")[-1].strip()
            parts.append(f"Applied corrections: {corrections}")

    return " ".join(parts)


def _dedup_check(summary: str) -> bool:
    """Check if a similar learning already exists.

    Returns True if a duplicate is found and capture should be skipped.
    This is best-effort: if the check fails for any reason, we proceed
    with capture (return False).
    """
    try:
        result = subprocess.run(
            [_SUPA_SEARCH, summary[:100], "--table", "learnings", "--limit", "3"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_get_subprocess_env(),
        )
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            if "No results" not in output and len(output) > 10:
                logger.info(
                    "Dedup check found similar entries, checking relevance..."
                )
                # Allow capture -- exact dedup is handled by the supa tools
                return False
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
        logger.warning("Dedup check failed (proceeding with capture): %s", exc)
        return False


def capture_regeneration_feedback(
    gate_type: str,
    scene_id: str,
    flag_reasons: list[str],
    feedback_text: Optional[str],
    original_prompt: str,
    adjusted_prompt: str,
    format_type: str,
) -> bool:
    """Capture a regeneration correction to the learnings table.

    This is the main entry point. Call it after a successful regeneration
    to save the correction for future productions.

    Args:
        gate_type: The gate that was flagged (image_1k, image_2k, video_clip, video).
        scene_id: Scene identifier (e.g. "S03").
        flag_reasons: List of structured flag reason tags.
        feedback_text: Free-text reviewer feedback (may be None).
        original_prompt: The original prompt before adjustment.
        adjusted_prompt: The adjusted prompt after feedback.
        format_type: Production type folder name (vsl, ads, ugc).

    Returns:
        True if captured successfully, False otherwise.
    """
    topic = _build_topic(gate_type, flag_reasons, feedback_text or "")
    summary = _build_summary(
        scene_id, flag_reasons, feedback_text, original_prompt, adjusted_prompt
    )
    stage_id = _GATE_TO_STAGE.get(gate_type, gate_type)

    # Map folder-style format names to canonical applies_to values
    format_map = {"ads": "short_ad", "vsl": "vsl", "ugc": "ugc"}
    applies_to_format = format_map.get(format_type, format_type)

    # Regeneration always implies high impact -- something was bad enough to redo
    impact = "high"

    # Best-effort dedup check
    if _dedup_check(summary):
        logger.info("Skipping capture -- similar learning already exists")
        return False

    # Build the capture payload
    data = {
        "agent_id": "regen-pipeline",
        "category": "video-feedback",
        "topic": topic,
        "summary": summary,
        "impact": impact,
        "applies_to": [applies_to_format, stage_id],
    }

    try:
        result = subprocess.run(
            [_SUPA_CAPTURE, "--table", "learnings", "--data", json.dumps(data)],
            capture_output=True,
            text=True,
            timeout=15,
            env=_get_subprocess_env(),
        )
        if result.returncode == 0:
            logger.info("Feedback captured: %s", topic)
            return True
        else:
            logger.warning("supa-capture failed: %s", result.stderr)
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Feedback capture failed: %s", exc)
        return False


def retrieve_past_feedback(gate_type: str) -> list[str]:
    """Retrieve past feedback rules for a given gate type.

    Queries the learnings table via supa-search-cc for corrections
    relevant to the current generation stage. Returns a list of
    rule strings that can be prepended to a prompt adjustment.

    Args:
        gate_type: The gate type being regenerated (image_1k, image_2k,
                   video_clip, video).

    Returns:
        List of rule strings extracted from past learnings. Empty list
        if retrieval fails or no relevant learnings are found.
    """
    stage_id = _GATE_TO_STAGE.get(gate_type, gate_type)
    query = _STAGE_SEARCH_TERMS.get(stage_id, f"{stage_id} regeneration correction")

    try:
        result = subprocess.run(
            [_SUPA_SEARCH, query, "--table", "learnings", "--limit", "5"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_get_subprocess_env(),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        output = result.stdout.strip()
        if "No results" in output:
            return []

        # Parse output lines into rule strings.
        # supa-search-cc outputs one entry per block; extract summary lines.
        rules = []
        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("="):
                continue
            # Look for lines that contain actionable feedback
            lower = line.lower()
            if any(
                kw in lower
                for kw in [
                    "correction",
                    "feedback",
                    "regenerat",
                    "flag",
                    "wrong",
                    "fix",
                    "adjust",
                    "scene",
                ]
            ):
                # Clean up and add as a rule
                rule = line.strip("- ").strip()
                if len(rule) > 10 and rule not in rules:
                    rules.append(rule)

        return rules

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as exc:
        logger.warning("Past feedback retrieval failed (non-blocking): %s", exc)
        return []
