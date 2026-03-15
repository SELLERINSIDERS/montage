"""LLM-based prompt rewriting for scene regeneration.

Replaces the naive string-concatenation approach (adjust_prompt) with
Gemini-powered prompt rewriting that encodes cinematic-director and
cinematographer methodology.

For image gates: applies the 7-Element Image Prompt Formula + Epic Scale
Doctrine via the image_rewrite_prompt.txt template.

For video gates: applies the 6-Rule Cinematic Video Prompt Standard +
camera plan alignment via the video_rewrite_prompt.txt template.

Falls back to the legacy adjust_prompt() concatenation if the LLM call
fails, so the regeneration pipeline never crashes.

Usage:
    from scripts.prompt_rewriter import rewrite_prompt, load_scene_context

    context = load_scene_context(project_dir, scene_id)
    new_prompt = rewrite_prompt(
        gate_type="image_1k",
        original_prompt=original,
        feedback_text="Lighting is too flat",
        flag_reasons=["Bad lighting"],
        script_context=context.get("script_context"),
        past_learnings=["Avoid flat overhead lighting on portrait scenes"],
    )
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Ensure API keys are available even if this module is imported standalone.
# Project .env contains GEMINI_API_KEY; optional EXTRA_ENV_FILE for Supabase creds.
_project_env = Path(__file__).resolve().parent.parent / ".env"
if _project_env.exists():
    load_dotenv(_project_env, override=False)
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    """Result of a prompt rewrite operation.

    Attributes:
        prompt: The rewritten (or fallback-adjusted) prompt string.
        method: ``"llm"`` if Gemini rewrote it, ``"fallback"`` if concatenation was used.
        error: Error message if the LLM failed and fallback was used, else None.
    """

    prompt: str
    method: str  # "llm" | "fallback"
    error: Optional[str] = None


# Template directory relative to this file
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Gate types that use image rewriting vs video rewriting
_IMAGE_GATES = {"image_1k", "image_2k"}
_VIDEO_GATES = {"video_clip", "video"}

# Gemini model for text rewriting (NOT the image model)
_REWRITE_MODEL = "gemini-2.5-flash"
_REWRITE_TIMEOUT = 60  # seconds — generous for thinking models with 1024-token budget


# --------------------------------------------------------------------------- #
# Template loading
# --------------------------------------------------------------------------- #


def _load_template(gate_type: str) -> str:
    """Load the appropriate system prompt template for the gate type.

    Args:
        gate_type: One of ``image_1k``, ``image_2k``, ``video_clip``, ``video``.

    Returns:
        Template string with placeholder markers.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    if gate_type in _IMAGE_GATES:
        template_path = _TEMPLATE_DIR / "image_rewrite_prompt.txt"
    elif gate_type in _VIDEO_GATES:
        template_path = _TEMPLATE_DIR / "video_rewrite_prompt.txt"
    else:
        raise ValueError(f"Unknown gate_type: {gate_type}")

    return template_path.read_text(encoding="utf-8")


def _fill_template(
    template: str,
    *,
    original_prompt: str,
    feedback_text: str | None,
    flag_reasons: list[str] | None,
    script_context: str | None = None,
    camera_plan: dict | None = None,
    image_description: str | None = None,
    past_learnings: list[str] | None = None,
    prompt_history: list[dict] | None = None,
) -> str:
    """Fill placeholders in the template with actual context.

    Uses simple string replacement for the ``{placeholder}`` markers.
    Missing values are replaced with ``"None provided."``
    """
    # Format flag reasons
    if flag_reasons:
        flag_str = ", ".join(flag_reasons)
    else:
        flag_str = "None provided."

    # Format past learnings
    if past_learnings:
        learnings_str = "\n".join(f"- {rule}" for rule in past_learnings)
    else:
        learnings_str = "None provided."

    # Format prompt history
    if prompt_history:
        history_parts = []
        for entry in prompt_history:
            version = entry.get("version", "?")
            text = entry.get("prompt_text", "")
            source = entry.get("source", "")
            history_parts.append(f"Version {version} ({source}): {text}")
        history_str = "\n".join(history_parts)
    else:
        history_str = "None -- this is the first rewrite."

    # Format camera plan (video only)
    if camera_plan:
        camera_str = json.dumps(camera_plan, indent=2)
    else:
        camera_str = "None provided."

    replacements = {
        "{original_prompt}": original_prompt or "None provided.",
        "{feedback_text}": feedback_text or "None provided.",
        "{flag_reasons}": flag_str,
        "{script_context}": script_context or "None provided.",
        "{past_learnings}": learnings_str,
        "{prompt_history}": history_str,
        "{camera_plan}": camera_str,
        "{image_description}": image_description or "None provided.",
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


# --------------------------------------------------------------------------- #
# LLM call
# --------------------------------------------------------------------------- #


def _call_gemini(prompt: str) -> str:
    """Call Gemini for text generation and return the response text.

    Uses ``gemini-2.5-flash`` for fast, high-quality text rewriting.
    Logs a warning if the call exceeds the timeout threshold but keeps
    the response (a slow valid rewrite beats fallback concatenation).

    Args:
        prompt: The full prompt (system + context filled in).

    Returns:
        Raw response text from Gemini.

    Raises:
        RuntimeError: If the API key is missing, the SDK is unavailable,
            or the response contains no text.
    """
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

    client = genai.Client(api_key=api_key)

    start = time.time()
    response = client.models.generate_content(
        model=_REWRITE_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT"],
            temperature=0.7,
            max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(
                thinking_budget=1024,
            ),
        ),
    )
    elapsed = time.time() - start

    if elapsed > _REWRITE_TIMEOUT:
        # Log a warning but DON'T discard the response — a slow valid rewrite
        # is better than falling back to concatenation.
        logger.warning(
            "Gemini rewrite took %.1fs (threshold: %ds) — response kept",
            elapsed,
            _REWRITE_TIMEOUT,
        )

    if not response.candidates or not response.candidates[0].content.parts:
        raise RuntimeError("Gemini returned no text content")

    # Gemini 2.5 (thinking models) may return multiple parts: thinking
    # parts followed by the actual text response. Extract the last text
    # part which contains the final output.
    text_parts = [
        p.text
        for p in response.candidates[0].content.parts
        if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
    ]

    if not text_parts:
        # Fallback: try the first part regardless
        return response.candidates[0].content.parts[-1].text

    return text_parts[-1]


def _clean_response(text: str) -> str:
    """Strip meta-commentary, markdown, and wrapping from LLM output.

    The template instructs the LLM to return only the clean prompt, but
    models sometimes add markdown code fences, quotes, or preamble.
    This function strips all of that.

    Args:
        text: Raw LLM response text.

    Returns:
        Clean prompt string ready for generation.
    """
    cleaned = text.strip()

    # Remove markdown code fences (```...```)
    if cleaned.startswith("```"):
        # Strip opening fence (with optional language tag)
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        # Strip closing fence
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    # Remove surrounding quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()

    # Remove common preamble patterns the LLM might add
    preamble_patterns = [
        r"^Here(?:'s| is) the (?:rewritten |new |updated )?(?:image |video |motion )?prompt[:\s]*\n*",
        r"^(?:Rewritten|Updated|New) (?:image |video |motion )?prompt[:\s]*\n*",
        r"^Prompt[:\s]*\n*",
    ]
    for pattern in preamble_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _strip_corrections(prompt: str) -> str:
    """Remove appended ``| CORRECTIONS:`` blocks from cascading fallback rewrites.

    When the LLM rewriter fails repeatedly, the fallback concatenation appends
    ``| CORRECTIONS: ...`` to the prompt. If the corrected prompt is later
    stored in ``scenes.prompt_text`` and used as the ``original_prompt`` for
    the next rewrite attempt, the corrections cascade infinitely.

    This helper strips all ``| CORRECTIONS:`` suffixes so the LLM always
    receives the clean base prompt.

    Args:
        prompt: Prompt string, possibly containing appended corrections.

    Returns:
        The prompt with all ``| CORRECTIONS:`` suffixes removed.
    """
    idx = prompt.find(" | CORRECTIONS:")
    return prompt[:idx].strip() if idx >= 0 else prompt


def rewrite_prompt(
    gate_type: str,
    original_prompt: str,
    feedback_text: str | None,
    flag_reasons: list[str] | None,
    script_context: str | None = None,
    camera_plan: dict | None = None,
    image_description: str | None = None,
    past_learnings: list[str] | None = None,
    prompt_history: list[dict] | None = None,
) -> RewriteResult:
    """Rewrite a generation prompt using LLM-based skill application.

    For image gates: applies cinematic-director + nano-banana methodology.
    For video gates: applies cinematographer + video-prompting-guide methodology.

    Returns a ``RewriteResult`` with the clean prompt AND the method used
    (``"llm"`` or ``"fallback"``), so callers can record the correct source
    in the audit trail.

    Falls back to the original prompt + basic corrections if the LLM call fails,
    but logs the failure at ERROR level so it is immediately visible.

    Args:
        gate_type: One of ``image_1k``, ``image_2k``, ``video_clip``, ``video``.
        original_prompt: The original scene prompt that produced the flagged asset.
        feedback_text: Free-text feedback from the reviewer.
        flag_reasons: List of structured flag reason tags.
        script_context: The scene's script/copy context from the master script.
        camera_plan: The camera_plan.json entry for this scene (video only).
        image_description: Description of the source image (video only).
        past_learnings: Rules from the learnings table (hard constraints).
        prompt_history: Previous prompt versions for iterative refinement.
            Each entry should have keys: version, prompt_text, source.

    Returns:
        A ``RewriteResult`` containing the prompt, method, and any error.
    """
    # Strip cascading corrections from previous fallback rewrites
    clean_prompt = _strip_corrections(original_prompt) if original_prompt else ""
    original_len = len(clean_prompt)

    if clean_prompt != (original_prompt or ""):
        logger.info(
            "Stripped cascading corrections from prompt (was %d chars, now %d)",
            len(original_prompt or ""),
            original_len,
        )

    try:
        # 1. Load and fill the template
        template = _load_template(gate_type)
        filled_prompt = _fill_template(
            template,
            original_prompt=clean_prompt,
            feedback_text=feedback_text,
            flag_reasons=flag_reasons,
            script_context=script_context,
            camera_plan=camera_plan,
            image_description=image_description,
            past_learnings=past_learnings,
            prompt_history=prompt_history,
        )

        # Observability: log the filled template (truncated)
        logger.info(
            "Sending to Gemini (%s): %.500s%s",
            gate_type,
            filled_prompt,
            "... [truncated]" if len(filled_prompt) > 500 else "",
        )

        # 2. Call Gemini for text rewriting
        raw_response = _call_gemini(filled_prompt)

        # 3. Clean the response
        rewritten = _clean_response(raw_response)

        # 4. Sanity checks
        if len(rewritten) < 20:
            raise ValueError(
                f"Rewritten prompt too short ({len(rewritten)} chars): "
                f"'{rewritten[:50]}'"
            )

        # Detect LLM refusals / placeholder responses (e.g. "I need more context")
        _REFUSAL_PATTERNS = [
            "awaiting", "cannot generate", "need more context",
            "unable to", "not enough information", "please provide",
            "cannot fulfill", "i cannot", "i can't",
        ]
        lower_rewritten = rewritten.lower()
        for pattern in _REFUSAL_PATTERNS:
            if pattern in lower_rewritten:
                raise ValueError(
                    f"LLM returned a refusal/placeholder instead of a prompt "
                    f"(matched '{pattern}'): '{rewritten[:100]}...'"
                )

        template_name = (
            "image_rewrite_prompt.txt"
            if gate_type in _IMAGE_GATES
            else "video_rewrite_prompt.txt"
        )
        logger.info(
            "LLM rewrite SUCCESS: template=%s original_len=%d new_len=%d output=%.500s%s",
            template_name,
            original_len,
            len(rewritten),
            rewritten,
            "... [truncated]" if len(rewritten) > 500 else "",
        )

        return RewriteResult(prompt=rewritten, method="llm")

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "LLM REWRITE FAILED — falling back to concatenation. "
            "This means feedback will NOT be properly integrated. Error: %s",
            exc,
            exc_info=True,
        )
        fallback_prompt = _fallback_adjust(
            clean_prompt, feedback_text, flag_reasons, past_learnings
        )
        logger.error(
            "Fallback concatenation result (%.500s%s)",
            fallback_prompt,
            "... [truncated]" if len(fallback_prompt) > 500 else "",
        )
        return RewriteResult(prompt=fallback_prompt, method="fallback", error=error_msg)


def _fallback_adjust(
    original_prompt: str,
    feedback_text: str | None,
    flag_reasons: list[str] | None,
    past_learnings: list[str] | None = None,
) -> str:
    """Legacy fallback: append corrections via string concatenation.

    Inlined here (not imported from regenerate_scene) to avoid a circular
    import between prompt_rewriter and regenerate_scene.
    """
    adjustments: list[str] = []

    if past_learnings:
        for rule in past_learnings:
            adjustments.append(f"Past learning: {rule}")

    if flag_reasons:
        # Inline version of _FLAG_REASON_MAP lookup -- only the generic
        # instruction matters for fallback; the LLM path handles specifics.
        for reason in flag_reasons:
            adjustments.append(f"Address: {reason}")

    if feedback_text:
        adjustments.append(f"Reviewer note: {feedback_text}")

    if not adjustments:
        return original_prompt

    return original_prompt + " | CORRECTIONS: " + "; ".join(adjustments)


# --------------------------------------------------------------------------- #
# Scene context loader
# --------------------------------------------------------------------------- #


def load_scene_context(
    project_dir: Path,
    scene_id: str,
) -> dict:
    """Load script context, camera plan, and prompt history for a scene.

    Reads production files from the project directory to gather all
    available context for prompt rewriting. Gracefully handles missing
    files -- returns whatever is available.

    Args:
        project_dir: Path to the project root (e.g., ``ads/my-project-v1``).
        scene_id: Scene identifier (e.g., ``scene_01``, ``S04c``).

    Returns:
        Dict with keys:
        - ``script_context``: Extracted section from master_script.md for this scene.
        - ``camera_plan``: Camera plan entry dict from camera_plan.json.
        - ``image_description``: Original image prompt from scene_prompts.md.
    """
    from video.kling.schema_validation import normalize_scene_id

    normalized = normalize_scene_id(scene_id)
    result: dict = {
        "script_context": None,
        "camera_plan": None,
        "image_description": None,
    }

    # --- Master script context ---
    master_script_path = project_dir / "copy" / "master_script.md"
    if master_script_path.exists():
        try:
            result["script_context"] = _extract_scene_section(
                master_script_path, scene_id, normalized
            )
        except Exception as exc:
            logger.debug("Could not extract master script section: %s", exc)

    # --- Camera plan ---
    camera_plan_path = project_dir / "prompts" / "camera_plan.json"
    if camera_plan_path.exists():
        try:
            camera_data = json.loads(camera_plan_path.read_text(encoding="utf-8"))
            scenes = camera_data.get("scenes", [])
            for entry in scenes:
                entry_scene = entry.get("scene", "")
                # Match by scene number: "01", "04c", etc.
                scene_num = _extract_scene_number(scene_id)
                if entry_scene == scene_num or entry_scene == scene_id or entry_scene == normalized:
                    result["camera_plan"] = entry
                    break
        except Exception as exc:
            logger.debug("Could not load camera plan: %s", exc)

    # --- Image prompt from scene_prompts.md ---
    for prompts_file in ("scene_prompts_final.md", "scene_prompts.md"):
        prompts_path = project_dir / "prompts" / prompts_file
        if prompts_path.exists():
            try:
                result["image_description"] = _extract_image_prompt(
                    prompts_path, scene_id, normalized
                )
                if result["image_description"]:
                    break
            except Exception as exc:
                logger.debug("Could not extract image prompt from %s: %s", prompts_file, exc)

    return result


# --------------------------------------------------------------------------- #
# File parsing helpers
# --------------------------------------------------------------------------- #


def _extract_scene_number(scene_id: str) -> str:
    """Extract the numeric part from a scene ID.

    Examples:
        ``scene_01`` -> ``01``
        ``S04c`` -> ``04c``
        ``scene_04a`` -> ``04a``
    """
    match = re.search(r"(\d+[a-z]?)", scene_id, re.IGNORECASE)
    return match.group(1) if match else scene_id


def _extract_scene_section(
    filepath: Path,
    scene_id: str,
    normalized: str,
) -> Optional[str]:
    """Extract a scene's section from a markdown file.

    Looks for headings containing the scene ID or number, then captures
    text until the next same-level heading.

    Returns the section text, or None if not found.
    """
    content = filepath.read_text(encoding="utf-8")
    scene_num = _extract_scene_number(scene_id)

    # Try to find a heading that matches this scene
    # Patterns: "## Scene 01", "### Scene 04a", "## scene_01", etc.
    # NOTE: Use {{2,3}} to produce literal {2,3} inside f-strings for regex quantifiers.
    patterns = [
        rf"^(#{{2,3}})\s+.*?(?:scene[\s_]*)?{re.escape(scene_num)}\b",
        rf"^(#{{2,3}})\s+.*?{re.escape(normalized)}\b",
        rf"^(#{{2,3}})\s+.*?{re.escape(scene_id)}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
        if match:
            heading_level = len(match.group(1))
            start = match.start()

            # Find the next heading at the same or higher level
            next_heading = re.search(
                rf"^#{{1,{heading_level}}}\s",
                content[match.end():],
                re.MULTILINE,
            )

            if next_heading:
                end = match.end() + next_heading.start()
            else:
                end = len(content)

            section = content[start:end].strip()
            # Truncate very long sections to keep the LLM context manageable
            if len(section) > 2000:
                section = section[:2000] + "\n... (truncated)"
            return section

    return None


def _extract_image_prompt(
    filepath: Path,
    scene_id: str,
    normalized: str,
) -> Optional[str]:
    """Extract the IMAGE PROMPT section for a scene from scene_prompts.md.

    Looks for the ``### IMAGE PROMPT`` heading within the scene's section,
    then captures the prompt text.

    Returns the prompt text, or None if not found.
    """
    # First, extract the full scene section
    section = _extract_scene_section(filepath, scene_id, normalized)
    if not section:
        return None

    # Find the IMAGE PROMPT subsection
    match = re.search(
        r"###\s+IMAGE\s+PROMPT\s*\n(.*?)(?=\n###|\n\*\*Negative\*\*|\Z)",
        section,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    return None
