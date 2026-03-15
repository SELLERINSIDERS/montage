"""Auto-push helper for image generation scripts.

After an image is saved to disk, call sync_generated_image() to:
1. Upload the image to Supabase Storage
2. Update the scene row with image_storage_path and thumbnail_storage_path
3. Update image_1k_status or image_2k_status to 'generated'
4. Log a generation_event for the real-time dashboard activity feed
5. Push updated manifest to sync aggregate counts

Usage:
    from scripts.image_sync import sync_generated_image
    sync_generated_image(
        local_path="ads/my-project-v1/images/v1/scene_01.png",
        scene_id="S01",
        format_type="ads",
        slug="my-project-v1",
        gate_type="image_1k",  # or "image_2k"
    )

All operations are non-blocking: failures log warnings but never crash the pipeline.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy singleton -- avoid importing DashboardSync at module level
# so this module can be imported in environments without supabase installed.
_sync_instance: Optional["DashboardSync"] = None  # type: ignore[name-defined]


def _get_sync():
    """Return a cached DashboardSync instance, creating on first call."""
    global _sync_instance
    if _sync_instance is None:
        try:
            from scripts.dashboard_sync import DashboardSync

            _sync_instance = DashboardSync()
        except Exception as exc:
            logger.warning("image_sync: could not create DashboardSync: %s", exc)
            # Return a disabled stub so callers can check .enabled
            _sync_instance = _DisabledSync()
    return _sync_instance


class _DisabledSync:
    """Stub returned when DashboardSync cannot be imported."""

    enabled = False


def sync_image_started(
    scene_id: str,
    format_type: str,
    slug: str,
    gate_type: str = "image_1k",
) -> None:
    """Log a generation_event marking the start of image generation for a scene.

    Args:
        scene_id: Scene identifier (e.g. "scene_01" or "S01").
        format_type: Production type folder name ("vsl", "ads", "ugc").
        slug: Project slug (e.g. "my-project-v1").
        gate_type: "image_1k" or "image_2k".
    """
    try:
        sync = _get_sync()
        if not sync.enabled:
            return

        from scripts.dashboard_sync import DashboardSync

        production_id = DashboardSync._production_id(format_type, slug)
        sync.push_generation_event(
            production_id,
            scene_id,
            "image_started",
            {"gate_type": gate_type},
        )
    except Exception as exc:
        logger.warning("image_sync: sync_image_started failed: %s", exc)


def sync_generated_image(
    local_path: str,
    scene_id: str,
    format_type: str,
    slug: str,
    gate_type: str = "image_1k",
    workflow_manifest_path: Optional[str] = None,
) -> None:
    """Upload a generated image to Supabase and update the scene row.

    This is the main entry point. Call it after saving an image to disk.

    Args:
        local_path: Path to the generated image on disk.
        scene_id: Scene identifier (e.g. "scene_01" or "S01").
        format_type: Production type folder name ("vsl", "ads", "ugc").
        slug: Project slug (e.g. "my-project-v1").
        gate_type: "image_1k" or "image_2k".
        workflow_manifest_path: Optional path to workflow-manifest.json to push
            aggregate counts after the scene update.
    """
    try:
        sync = _get_sync()
        if not sync.enabled:
            return

        from scripts.dashboard_sync import DashboardSync

        filename = os.path.basename(local_path)

        # Compute storage path based on gate type
        if gate_type == "image_2k":
            storage_path = f"{format_type}/{slug}/images/2k/{filename}"
        else:
            storage_path = f"{format_type}/{slug}/images/v1/{filename}"

        # 1. Upload image to Supabase Storage
        upload_result = sync.upload_asset(local_path, storage_path)
        if upload_result is None:
            logger.warning(
                "image_sync: upload_asset returned None for %s", local_path
            )
            return

        # 2. Update scene row with storage paths and status
        production_id = DashboardSync._production_id(format_type, slug)

        scene_update: dict = {
            "image_storage_path": storage_path,
            "thumbnail_storage_path": storage_path,  # images ARE thumbnails at 1K
            "asset_state": "generated",
        }

        if gate_type == "image_2k":
            scene_update["image_2k_status"] = "generated"
        else:
            scene_update["image_1k_status"] = "generated"

        sync.push_scene_update(production_id, scene_id, scene_update)

        # 3. Insert generation_event for real-time activity feed
        sync.push_generation_event(
            production_id,
            scene_id,
            "image_completed",
            {
                "gate_type": gate_type,
                "storage_path": storage_path,
                "filename": filename,
            },
        )

        # 4. Optionally push manifest to sync aggregate counts
        if workflow_manifest_path and os.path.exists(workflow_manifest_path):
            sync.push_manifest(workflow_manifest_path)

        logger.info(
            "image_sync: synced %s scene=%s to %s",
            gate_type,
            scene_id,
            storage_path,
        )

    except Exception as exc:
        logger.warning("image_sync: sync_generated_image failed: %s", exc)
