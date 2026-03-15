"""Backfill video_prompt column in scenes table from kling_manifest.json.

One-time migration script: reads the Kling manifest for each production
and populates scenes.video_prompt so the regeneration pipeline and
auto-video trigger have the original video motion prompt available.

Usage:
    python scripts/backfill_video_prompts.py
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# DB format -> filesystem directory
FORMAT_DIR_MAP = {"vsl": "vsl", "ad": "ads", "ugc": "ugc"}


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        return

    sb = create_client(url, key)

    # Get all active productions
    prods = sb.table("productions").select("id, format, slug").execute()
    if not prods.data:
        logger.info("No productions found")
        return

    total_updated = 0

    for prod in prods.data:
        prod_id = prod["id"]
        fmt = prod["format"]
        slug = prod["slug"]
        fs_dir = FORMAT_DIR_MAP.get(fmt, fmt)
        project_dir = Path(fs_dir) / slug

        manifest_path = project_dir / "manifest" / "kling_manifest.json"
        if not manifest_path.exists():
            logger.info("No kling_manifest.json for %s/%s — skipping", fmt, slug)
            continue

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, list):
            logger.warning("Unexpected manifest format for %s/%s — skipping", fmt, slug)
            continue

        for entry in manifest_data:
            scene_id = entry.get("scene_id", "")
            video_prompt = entry.get("video_prompt", "")
            if not scene_id or not video_prompt:
                continue

            # Update scenes table
            try:
                result = (
                    sb.table("scenes")
                    .update({"video_prompt": video_prompt})
                    .eq("production_id", prod_id)
                    .eq("scene_id", scene_id)
                    .is_("video_prompt", "null")  # Only backfill if not already set
                    .execute()
                )
                if result.data:
                    total_updated += len(result.data)
                    logger.info("Updated %s/%s scene %s", fmt, slug, scene_id)
            except Exception as exc:
                logger.warning("Failed to update %s: %s", scene_id, exc)

    logger.info("Backfill complete: %d scenes updated", total_updated)


if __name__ == "__main__":
    main()
