"""Feedback-aware scene regeneration dispatcher.

Called by job_poller.py when a regeneration job is claimed. Reads the feedback,
rewrites the prompt using LLM-based skill application, dispatches generation,
and pushes results back to Supabase.

Prompt rewriting uses ``scripts.prompt_rewriter.rewrite_prompt`` which sends the
original prompt, feedback, flag reasons, script context, camera plan, and prompt
history to an LLM that produces a single clean prompt with corrections baked in.
If the LLM call fails, falls back to the legacy concatenation method
(``_fallback_adjust_prompt``).

Usage (standalone for testing):
    python scripts/regenerate_scene.py --job-id <uuid>
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load project .env first, then optional EXTRA_ENV_FILE (e.g. for Supabase creds)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

from scripts.dashboard_sync import DashboardSync

try:
    from scripts.prompt_rewriter import rewrite_prompt, load_scene_context, RewriteResult
except ImportError:
    rewrite_prompt = None  # type: ignore[assignment]
    load_scene_context = None  # type: ignore[assignment]
    RewriteResult = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Format-to-directory mapping
# --------------------------------------------------------------------------- #

# DB stores 'ad' but the filesystem uses 'ads/' as the folder root.
_FORMAT_DIR_MAP: dict[str, str] = {
    "vsl": "vsl",
    "ad": "ads",
    "ugc": "ugc",
}


def _format_to_dir(format_type: str) -> str:
    """Map a production format to its filesystem directory name."""
    return _FORMAT_DIR_MAP.get(format_type, format_type)


# --------------------------------------------------------------------------- #
# Flag-reason to corrective instruction mapping
# --------------------------------------------------------------------------- #

_FLAG_REASON_MAP: dict[str, str] = {
    # Dashboard flag reasons (current vocabulary)
    "Wrong composition": "Adjust composition, framing, and camera angle to match the scene description",
    "Bad lighting": "Correct the lighting, shadows, and atmosphere to match the intended mood",
    "Character issue": "Fix character pose, expression, identity consistency, and appearance",
    "Motion artifact": "Remove motion artifacts, ensure smooth natural movement",
    "Wrong scale": "Fix scale and proportions of all elements in the scene",
    "Text/overlay issue": "Remove any visible text, letters, logos, or watermarks from the image",
    "Continuity break": "Maintain visual continuity with surrounding scenes in style, color, and setting",
    "Other": "Address the specific issue described in the reviewer's notes",
    # Legacy snake_case keys (backwards compatibility with any existing data)
    "wrong_pose": "Correct the character pose as described",
    "wrong_expression": "Fix facial expression to match the intended emotion",
    "wrong_setting": "Adjust the background/setting environment",
    "wrong_lighting": "Correct the lighting and atmosphere",
    "wrong_framing": "Adjust camera framing and composition",
    "low_quality": "Improve overall image quality and detail",
    "anachronistic": "Remove any anachronistic or out-of-period elements",
    "text_visible": "Remove any visible text, letters, or watermarks",
    "identity_shift": "Maintain consistent character identity and appearance",
}


# --------------------------------------------------------------------------- #
# Prompt adjustment
# --------------------------------------------------------------------------- #


def _fallback_adjust_prompt(
    original_prompt: str,
    feedback_text: Optional[str],
    flag_reasons: Optional[list[str]],
    past_rules: Optional[list[str]] = None,
) -> str:
    """Legacy fallback: adjust a prompt by concatenating corrections.

    Used when the LLM-based prompt rewriter is unavailable or fails.
    Appends corrective instructions derived from flag_reasons, free-text
    feedback, and past learnings. Returns the original prompt unchanged
    if no feedback or rules are present.

    Args:
        original_prompt: The original scene prompt.
        feedback_text: Free-text feedback from the reviewer.
        flag_reasons: List of structured flag reason tags.
        past_rules: Optional list of rule strings from past learnings
            to prepend to the corrections block.

    Returns:
        Adjusted prompt string.
    """
    adjustments: list[str] = []

    # Prepend past learnings as rules (if available)
    if past_rules:
        for rule in past_rules:
            adjustments.append(f"Past learning: {rule}")

    if flag_reasons:
        for reason in flag_reasons:
            mapped = _FLAG_REASON_MAP.get(reason)
            if mapped:
                adjustments.append(mapped)
            else:
                adjustments.append(f"Address: {reason}")

    if feedback_text:
        adjustments.append(f"Reviewer note: {feedback_text}")

    if not adjustments:
        return original_prompt

    adjustment_block = " | CORRECTIONS: " + "; ".join(adjustments)
    return original_prompt + adjustment_block


# Backwards-compatible alias — tests and prompt_rewriter import this name.
adjust_prompt = _fallback_adjust_prompt


# --------------------------------------------------------------------------- #
# Prompt version audit trail
# --------------------------------------------------------------------------- #


def _save_prompt_version(
    sync: DashboardSync,
    production_id: str,
    scene_id: str,
    prompt_text: str,
    version: int,
    source: str = "feedback_adjusted",
    feedback_reference: Optional[str] = None,
) -> None:
    """Save a prompt version to the audit trail table."""
    if not sync.enabled:
        return
    try:
        sync.client.table("prompt_versions").upsert(
            {
                "production_id": production_id,
                "scene_id": scene_id,
                "version": version,
                "prompt_text": prompt_text,
                "source": source,
                "feedback_reference": feedback_reference,
            },
            on_conflict="production_id,scene_id,version",
        ).execute()
    except Exception as exc:
        logger.warning("Failed to save prompt version: %s", exc)


def _get_current_prompt_version(
    sync: DashboardSync, production_id: str, scene_id: str
) -> int:
    """Get the current prompt version number for a scene (defaults to 1)."""
    if not sync.enabled:
        return 1
    try:
        result = (
            sync.client.table("scenes")
            .select("prompt_version")
            .eq("production_id", production_id)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )
        return (result.data or {}).get("prompt_version", 1)
    except Exception:
        return 1


# --------------------------------------------------------------------------- #
# Generation dispatchers
# --------------------------------------------------------------------------- #


def _regenerate_image(
    prompt: str,
    scene_id: str,
    project_dir: Path,
    gate_type: str,
) -> Path:
    """Regenerate a scene image using Nano Banana (Gemini).

    Args:
        prompt: Adjusted prompt string.
        scene_id: Scene identifier.
        project_dir: Project root directory (e.g. ``ads/my-project-v1``).
        gate_type: ``"image_1k"`` or ``"image_2k"``.

    Returns:
        Path to the saved image file.

    Raises:
        RuntimeError: If Gemini is unavailable or returns no image data.
    """
    from video.kling.schema_validation import normalize_scene_id

    file_id = normalize_scene_id(scene_id)
    if gate_type == "image_2k":
        out_dir = project_dir / "images" / "2k"
    else:
        out_dir = project_dir / "images" / "v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{file_id}_regen.png"

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. "
            "Install with: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY or GOOGLE_API_KEY set")

    image_size = "2K" if gate_type == "image_2k" else "1K"
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-3.1-flash-image-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16",
                image_size=image_size,
            ),
        ),
    )

    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                out_path.write_bytes(part.inline_data.data)
                return out_path

    raise RuntimeError("No image data in Gemini response")


def _regenerate_video(
    prompt: str,
    scene_id: str,
    project_dir: Path,
    sync: "DashboardSync",
    production_id: str,
    scene_context: dict | None = None,
) -> Path:
    """Regenerate a scene video using Kling AI (image-to-video).

    Finds the most recent source image for the scene and submits it
    to KlingClient for video synthesis. Falls back to downloading the
    image from Supabase Storage if no local file is found.

    Uses camera plan data for video generation parameters (mode, duration,
    cfg_scale) when available.

    Args:
        prompt: Adjusted prompt string.
        scene_id: Scene identifier.
        project_dir: Project root directory.
        sync: DashboardSync instance for Supabase Storage fallback.
        production_id: Production UUID for Storage lookups.
        scene_context: Optional dict with camera_plan entry for this scene.

    Returns:
        Path to the saved video file.

    Raises:
        RuntimeError: If no source image is found or KlingClient is unavailable.
    """
    from video.kling.schema_validation import normalize_scene_id

    file_id = normalize_scene_id(scene_id)
    out_dir = project_dir / "video" / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{file_id}_regen.mp4"

    # Locate a source image for the scene (local disk first, then Storage)
    image_dir = project_dir / "images" / "v1"
    image_path = _find_scene_image(image_dir, scene_id)
    if image_path is None:
        logger.info("No local image for %s — downloading from Supabase Storage", scene_id)
        image_path = _download_image_from_storage(
            sync, production_id, scene_id, project_dir
        )
    if image_path is None:
        raise RuntimeError(f"No source image found for {scene_id} (checked disk and Storage)")

    # Validate image file
    file_size = image_path.stat().st_size
    if file_size == 0:
        raise RuntimeError(f"Source image {image_path} is empty (0 bytes)")
    if file_size > 10 * 1024 * 1024:
        raise RuntimeError(
            f"Source image {image_path} is {file_size / 1048576:.1f}MB, exceeds 10MB Kling limit"
        )

    try:
        from video.kling.api_client import KlingClient
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "KlingClient or PIL not available. "
            "Check video/kling/api_client.py and Pillow installation."
        )

    client = KlingClient()

    img = Image.open(image_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    # Use camera plan parameters if available, otherwise defaults
    camera_plan = (scene_context or {}).get("camera_plan") or {}
    duration = camera_plan.get("duration", 5)
    mode = camera_plan.get("mode", "std")
    cfg_scale = camera_plan.get("cfg_scale", 0.4)

    result_path = client.image_to_video(
        image_bytes=image_bytes,
        prompt=prompt,
        output_path=str(out_path),
        negative_prompt=(
            "text, words, letters, logos, watermarks, UI elements, "
            "cartoonish, illustrated style, blurry, distorted, morphing faces"
        ),
        cfg_scale=cfg_scale,
        duration=duration,
        mode=mode,
    )
    return Path(result_path)


def _find_scene_image(image_dir: Path, scene_id: str) -> Optional[Path]:
    """Find the best available image file for a scene.

    Checks for regenerated images first (``_regen`` suffix), then originals.
    Supports .png, .jpg, and .jpeg extensions.

    If the exact ``scene_id`` doesn't match any file, falls back to the
    normalized form (e.g. ``S04c`` -> ``scene_04c``) so that short-form
    and long-form IDs both resolve to the same asset on disk.

    Returns:
        Path to the image file, or None if not found.
    """
    from video.kling.schema_validation import normalize_scene_id

    normalized = normalize_scene_id(scene_id)
    # Try raw scene_id first, then normalized form (skip duplicate if same)
    ids_to_try = [scene_id] if scene_id == normalized else [scene_id, normalized]

    for sid in ids_to_try:
        for suffix in ("_regen", ""):
            for ext in (".png", ".jpg", ".jpeg"):
                candidate = image_dir / f"{sid}{suffix}{ext}"
                if candidate.exists():
                    return candidate
    return None


# --------------------------------------------------------------------------- #
# Video prompt recovery from disk
# --------------------------------------------------------------------------- #


def _recover_video_prompt(
    project_dir: Path,
    scene_id: str,
    scene_context: dict,
) -> str:
    """Recover the original video prompt when not stored in the DB.

    Tries these sources in order:
    1. kling_manifest.json — has the exact video_prompt used in production
    2. Camera plan context — can construct a basic motion prompt

    Args:
        project_dir: Project root directory.
        scene_id: Normalized scene identifier.
        scene_context: Dict from load_scene_context (may contain camera_plan).

    Returns:
        The recovered video prompt string, or empty string if unrecoverable.
    """
    from video.kling.schema_validation import normalize_scene_id

    normalized = normalize_scene_id(scene_id)

    # 1. Try kling_manifest.json
    manifest_path = project_dir / "manifest" / "kling_manifest.json"
    if manifest_path.exists():
        try:
            import json

            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            scenes_list = manifest_data if isinstance(manifest_data, list) else []
            for entry in scenes_list:
                entry_id = entry.get("scene_id", "")
                if entry_id == scene_id or entry_id == normalized:
                    vp = entry.get("video_prompt", "")
                    if vp:
                        return vp
        except Exception as exc:
            logger.debug("Could not load kling_manifest.json: %s", exc)

    # 2. Try camera plan context (construct a basic prompt from motion data)
    camera_plan = scene_context.get("camera_plan")
    if camera_plan:
        camera_type = camera_plan.get("camera_type", "static")
        motion_elements = camera_plan.get("motion_elements", [])
        motion_reason = camera_plan.get("motion_reason", "")
        parts = [f"Camera: {camera_type}."]
        if motion_reason:
            parts.append(motion_reason)
        if motion_elements:
            parts.append("Motion: " + ", ".join(motion_elements) + ".")
        return " ".join(parts)

    return ""


def _download_image_from_storage(
    sync: "DashboardSync",
    production_id: str,
    scene_id: str,
    project_dir: Path,
) -> Optional[Path]:
    """Download the scene image from Supabase Storage to local disk.

    Used as a fallback when the local image file is missing (e.g., after
    a regen in a previous session where the local file was saved to a
    different directory path).

    Returns:
        Path to the downloaded image file, or None if download failed.
    """
    try:
        from video.kling.schema_validation import normalize_scene_id

        file_id = normalize_scene_id(scene_id)
        result = (
            sync.client.table("scenes")
            .select("image_storage_path")
            .eq("production_id", production_id)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )
        storage_path = (result.data or {}).get("image_storage_path")
        if not storage_path:
            return None

        # Download from Supabase Storage
        data = sync.client.storage.from_("production-assets").download(storage_path)
        if not data:
            return None

        # Save to local disk
        out_dir = project_dir / "images" / "v1"
        out_dir.mkdir(parents=True, exist_ok=True)
        local_path = out_dir / f"{file_id}_regen.png"
        local_path.write_bytes(data)
        logger.info(
            "Downloaded source image from storage: %s → %s",
            storage_path,
            local_path,
        )
        return local_path
    except Exception as exc:
        logger.warning("Failed to download image from storage: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Main regeneration entry point
# --------------------------------------------------------------------------- #


def regenerate(job: dict, sync: DashboardSync) -> None:
    """Execute a regeneration job end-to-end.

    This is the main entry point called by job_poller.py. It:
    0. Resolves the project directory from the production record.
    1. Retrieves past feedback learnings for the current gate stage.
    2. Loads scene context (script, camera plan) from disk.
    3. Loads prompt history from the prompt_versions table.
    4. Rewrites the prompt via LLM-based skill application (falls back
       to legacy concatenation if the rewriter is unavailable).
    5. Saves a prompt_versions entry for audit trail.
    6. Dispatches the appropriate generation (image or video).
    7. Uploads the result to Supabase Storage and updates the scene row.
    8. Marks the job as completed.
    9. Fires generation events for the real-time dashboard.
    10. Captures the correction to the learnings table.

    Args:
        job: Regeneration job dict from the regeneration_queue table.
        sync: Active DashboardSync instance.

    Raises:
        Exception: Re-raised after marking the job as failed so the poller
            knows the job did not succeed.
    """
    from video.kling.schema_validation import normalize_scene_id

    scene_id = normalize_scene_id(job["scene_id"])
    production_id = job["production_id"]
    gate_type = job["gate_type"]
    feedback_text = job.get("feedback_text")
    flag_reasons = job.get("flag_reasons") or []
    original_prompt = job.get("original_prompt") or ""
    job_id = job["id"]
    attempt_count = job.get("attempt_count", 0) + 1

    logger.info(
        "Regenerating scene=%s gate=%s job=%s attempt=%d",
        scene_id,
        gate_type,
        job_id,
        attempt_count,
    )

    # Mark job as processing
    try:
        sync.client.table("regeneration_queue").update(
            {"status": "processing", "attempt_count": attempt_count}
        ).eq("id", job_id).execute()
    except Exception as exc:
        logger.warning("Failed to update job status to processing: %s", exc)

    # Update scene asset_state
    sync.push_scene_update(production_id, scene_id, {"asset_state": "regenerating"})

    # Fire regen_started event
    sync.push_generation_event(
        production_id,
        scene_id,
        "regen_started",
        {
            "gate_type": gate_type,
            "job_id": job_id,
            "feedback": feedback_text,
            "flag_reasons": flag_reasons,
        },
    )

    try:
        # 0. Resolve project directory from production record (needed by context loader)
        prod_result = (
            sync.client.table("productions")
            .select("format, slug")
            .eq("id", production_id)
            .single()
            .execute()
        )
        if not prod_result.data:
            raise RuntimeError(f"Production {production_id} not found")

        format_type = prod_result.data["format"]
        slug = prod_result.data["slug"]
        project_dir = Path(_format_to_dir(format_type)) / slug

        # 1. Retrieve past feedback for this stage to inform prompt rewriting
        past_rules: list[str] = []
        try:
            from scripts.feedback_capture import retrieve_past_feedback

            past_rules = retrieve_past_feedback(gate_type)
            if past_rules:
                logger.info(
                    "Retrieved %d past learnings for %s", len(past_rules), gate_type
                )
        except Exception as exc:
            logger.warning("Past feedback retrieval failed (non-blocking): %s", exc)

        # 2. Load scene context (script, camera plan, prompt history)
        scene_context: dict = {}
        try:
            if load_scene_context is not None:
                scene_context = load_scene_context(project_dir, scene_id)
            else:
                logger.info("load_scene_context not available (prompt_rewriter not installed)")
        except Exception as exc:
            logger.warning("Scene context loading failed (non-blocking): %s", exc)

        # 2b. Recover original video prompt from disk when missing
        #     The DB may not have video_prompt populated yet, so we fall back
        #     to reading from kling_manifest.json or constructing from camera plan.
        if not original_prompt and gate_type in ("video_clip", "video"):
            original_prompt = _recover_video_prompt(project_dir, scene_id, scene_context)
            if original_prompt:
                logger.info(
                    "Recovered video prompt from disk for scene=%s (len=%d)",
                    scene_id,
                    len(original_prompt),
                )
            else:
                logger.warning(
                    "No video prompt found for scene=%s — LLM will generate from scratch "
                    "using camera plan and feedback context",
                    scene_id,
                )

        # 3. Load prompt history from prompt_versions table
        prompt_history: list[dict] = []
        try:
            pv_result = (
                sync.client.table("prompt_versions")
                .select("version, prompt_text, source, feedback_reference")
                .eq("production_id", production_id)
                .eq("scene_id", scene_id)
                .order("version", desc=True)
                .limit(5)
                .execute()
            )
            prompt_history = pv_result.data or []
        except Exception as exc:
            logger.warning("Prompt history retrieval failed (non-blocking): %s", exc)

        # 4. Rewrite prompt using LLM-based skill application (with fallback)
        rewrite_method = "fallback"  # Track which method produced the prompt
        if rewrite_prompt is not None:
            try:
                result = rewrite_prompt(
                    gate_type=gate_type,
                    original_prompt=original_prompt,
                    feedback_text=feedback_text,
                    flag_reasons=flag_reasons,
                    script_context=scene_context.get("script_context"),
                    camera_plan=scene_context.get("camera_plan"),
                    image_description=scene_context.get("image_description"),
                    past_learnings=past_rules,
                    prompt_history=prompt_history,
                )
                adjusted_prompt = result.prompt
                rewrite_method = result.method
                if result.method == "llm":
                    logger.info("Prompt rewritten via LLM skill for scene=%s", scene_id)
                else:
                    logger.warning(
                        "Prompt rewrite used FALLBACK concatenation for scene=%s "
                        "(error: %s). Feedback may not be properly integrated.",
                        scene_id,
                        result.error,
                    )
            except Exception as exc:
                logger.warning(
                    "LLM prompt rewrite call failed, falling back to concatenation: %s", exc
                )
                adjusted_prompt = _fallback_adjust_prompt(
                    original_prompt, feedback_text, flag_reasons, past_rules
                )
                rewrite_method = "fallback"
        else:
            logger.info("prompt_rewriter not available, using fallback concatenation")
            adjusted_prompt = _fallback_adjust_prompt(
                original_prompt, feedback_text, flag_reasons, past_rules
            )
            rewrite_method = "fallback"

        # Persist adjusted prompt on the job record
        try:
            sync.client.table("regeneration_queue").update(
                {"adjusted_prompt": adjusted_prompt}
            ).eq("id", job_id).execute()
        except Exception:
            pass  # Non-critical -- the prompt is also saved in prompt_versions

        # 5. Save prompt version for audit trail
        #    Use the actual rewrite method as the source so we can distinguish
        #    LLM rewrites from fallback concatenations in the audit trail.
        current_version = _get_current_prompt_version(sync, production_id, scene_id)
        new_version = current_version + 1

        prompt_source = "skill_rewritten" if rewrite_method == "llm" else "feedback_adjusted"
        feedback_ref = (
            f"job:{job_id} | {feedback_text or ''} | {','.join(flag_reasons)}"
        )
        _save_prompt_version(
            sync,
            production_id,
            scene_id,
            adjusted_prompt,
            new_version,
            source=prompt_source,
            feedback_reference=feedback_ref,
        )

        # 6. Dispatch generation based on gate_type
        if gate_type in ("image_1k", "image_2k"):
            result_path = _regenerate_image(
                adjusted_prompt, scene_id, project_dir, gate_type
            )
        elif gate_type in ("video_clip", "video"):
            result_path = _regenerate_video(
                adjusted_prompt, scene_id, project_dir,
                sync=sync,
                production_id=production_id,
                scene_context=scene_context,
            )
        else:
            raise ValueError(f"Unknown gate_type for regeneration: {gate_type}")

        # 7. Upload result and update scene
        _upload_and_update_scene(
            sync=sync,
            production_id=production_id,
            scene_id=scene_id,
            gate_type=gate_type,
            result_path=result_path,
            format_type=format_type,
            slug=slug,
            adjusted_prompt=adjusted_prompt,
            new_version=new_version,
            attempt_count=attempt_count,
        )

        # 8. Mark job completed
        sync.complete_regeneration_job(job_id, success=True)

        # 9. Fire completion event
        sync.push_generation_event(
            production_id,
            scene_id,
            "regen_completed",
            {
                "gate_type": gate_type,
                "job_id": job_id,
                "new_version": new_version,
            },
        )

        # 10. Capture correction to learnings table for future productions
        try:
            from scripts.feedback_capture import capture_regeneration_feedback

            capture_regeneration_feedback(
                gate_type=gate_type,
                scene_id=scene_id,
                flag_reasons=flag_reasons,
                feedback_text=feedback_text,
                original_prompt=original_prompt,
                adjusted_prompt=adjusted_prompt,
                format_type=format_type,
            )
        except Exception as exc:
            logger.warning("Feedback capture failed (non-blocking): %s", exc)

        logger.info(
            "Regeneration complete: scene=%s gate=%s version=%d",
            scene_id,
            gate_type,
            new_version,
        )

    except Exception as exc:
        logger.error(
            "Regeneration failed: scene=%s error=%s", scene_id, exc, exc_info=True
        )
        sync.push_scene_update(production_id, scene_id, {"asset_state": "failed"})
        sync.complete_regeneration_job(
            job_id, success=False, error_message=str(exc)
        )
        sync.push_generation_event(
            production_id,
            scene_id,
            "error",
            {"gate_type": gate_type, "job_id": job_id, "error": str(exc)},
        )
        raise


def _upload_and_update_scene(
    *,
    sync: DashboardSync,
    production_id: str,
    scene_id: str,
    gate_type: str,
    result_path: Path,
    format_type: str,
    slug: str,
    adjusted_prompt: str,
    new_version: int,
    attempt_count: int,
) -> None:
    """Upload the regenerated asset and update the scene row.

    Handles both image and video gate types with the appropriate upload
    method and scene column updates.
    """
    common_update: dict = {
        "asset_state": "generated",
        "prompt_version": new_version,
    }
    # Store the prompt in the correct column based on gate type
    if gate_type in ("video_clip", "video"):
        common_update["video_prompt"] = adjusted_prompt
    else:
        common_update["prompt_text"] = adjusted_prompt

    if gate_type in ("image_1k", "image_2k"):
        base_storage_path = f"{format_type}/{slug}/images/v1/{scene_id}.png"
        new_path = sync.upload_scene_image(
            production_id,
            scene_id,
            str(result_path),
            base_storage_path,
            clear_flags=True,
            gate_type=gate_type,
        )
        if new_path:
            sync.push_scene_update(production_id, scene_id, common_update)

    elif gate_type in ("video_clip", "video"):
        storage_path = f"{format_type}/{slug}/video/clips/{scene_id}_regen.mp4"
        sync.upload_asset(str(result_path), storage_path)
        sync.push_scene_update(
            production_id,
            scene_id,
            {
                **common_update,
                "video_storage_path": storage_path,
                "video_status": "generated",
                "current_gate": f"{gate_type}:generated",
                "flag_reasons": [],
                "feedback_video": None,
            },
        )


# --------------------------------------------------------------------------- #
# Standalone CLI for testing
# --------------------------------------------------------------------------- #


def main():
    """Regenerate a specific job by ID (for testing/manual dispatch)."""
    parser = argparse.ArgumentParser(
        description="Regenerate a scene from a specific job ID"
    )
    parser.add_argument(
        "--job-id", required=True, help="UUID of the regeneration job"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    sync = DashboardSync()
    if not sync.enabled:
        logger.error("DashboardSync is disabled")
        sys.exit(1)

    result = (
        sync.client.table("regeneration_queue")
        .select("*")
        .eq("id", args.job_id)
        .single()
        .execute()
    )
    if not result.data:
        logger.error("Job %s not found", args.job_id)
        sys.exit(1)

    regenerate(result.data, sync)


if __name__ == "__main__":
    main()
