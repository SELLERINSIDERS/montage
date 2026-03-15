"""
Sync Kling video clips to Supabase dashboard.

Uploads each clip to production-assets bucket and updates the scenes table
with video_storage_path and video_status. Configure SLUG, PRODUCTION_ID,
and paths below for your project.
"""
import os
import sys
import uuid
from pathlib import Path

# Load env — set EXTRA_ENV_FILE to load additional credentials
from dotenv import load_dotenv  # noqa: E402
load_dotenv()
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

try:
    from supabase import create_client
except ImportError:
    print("ERROR: supabase package not installed. Run: pip install supabase")
    sys.exit(1)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Production identity
FORMAT = "ad"
SLUG = "my-project-v1"  # TODO: Set your project slug
PRODUCTION_ID = ""  # TODO: Set your Supabase production UUID
BUCKET = "production-assets"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIPS_DIR = PROJECT_ROOT / f"ads/{SLUG}/video/clips"
IMAGES_DIR = PROJECT_ROOT / f"ads/{SLUG}/images/v1"

SCENES = [
    ("scene_01", 0),
    ("scene_02", 1),
    ("scene_03", 2),
    ("scene_04a", 3),
    ("scene_04b", 4),
    ("scene_04c", 5),
    ("scene_05", 6),
    ("scene_06", 7),
    ("scene_07", 8),
    ("scene_08", 9),
    ("scene_09", 10),
    ("scene_10", 11),
]

def ensure_production():
    """Update the production row stage to Video Gen."""
    client.table("productions").update({
        "current_phase": "video_generation",
        "current_stage": "Video Gen",
        "updated_at": "now()",
    }).eq("id", PRODUCTION_ID).execute()
    print(f"✓ Production stage updated: {PRODUCTION_ID}")

def upload_file(local_path: Path, storage_path: str) -> bool:
    """Upload a file to Supabase Storage. Returns True on success."""
    try:
        with open(local_path, "rb") as f:
            content_type = "video/mp4" if local_path.suffix == ".mp4" else "image/png"
            client.storage.from_(BUCKET).upload(
                path=storage_path,
                file=f,
                file_options={"upsert": "true", "content-type": content_type},
            )
        return True
    except Exception as e:
        print(f"  ✗ Upload failed: {e}")
        return False

def sync_scene(scene_id: str, scene_index: int):
    print(f"\n[{scene_id}]")

    # Paths
    clip_path = CLIPS_DIR / f"{scene_id}.mp4"
    image_path = IMAGES_DIR / f"{scene_id}.png"
    video_storage = f"{SLUG}/video/clips/{scene_id}.mp4"
    image_storage = f"{SLUG}/images/v1/{scene_id}.png"

    # Upload video clip
    video_ok = False
    if clip_path.exists():
        size_mb = clip_path.stat().st_size / 1_048_576
        print(f"  Uploading clip ({size_mb:.1f}MB) → {video_storage}")
        video_ok = upload_file(clip_path, video_storage)
        if video_ok:
            print(f"  ✓ Clip uploaded")
    else:
        print(f"  ✗ Clip not found: {clip_path}")

    # Upload image (for thumbnail/reference)
    image_ok = False
    if image_path.exists():
        size_mb = image_path.stat().st_size / 1_048_576
        print(f"  Uploading image ({size_mb:.1f}MB) → {image_storage}")
        image_ok = upload_file(image_path, image_storage)
        if image_ok:
            print(f"  ✓ Image uploaded")

    # Upsert scene row
    scene_row = {
        "production_id": PRODUCTION_ID,
        "scene_id": scene_id,
        "scene_index": scene_index,
        "updated_at": "now()",
    }
    if video_ok:
        scene_row["video_storage_path"] = video_storage
        scene_row["video_status"] = "completed"
    if image_ok:
        scene_row["image_storage_path"] = image_storage
        scene_row["thumbnail_storage_path"] = image_storage
        scene_row["image_1k_status"] = "approved"

    client.table("scenes").upsert(scene_row, on_conflict="production_id,scene_id").execute()
    print(f"  ✓ Scene row updated in DB")

def main():
    print("=" * 60)
    print(f"Syncing {SLUG} clips to dashboard")
    print(f"Production ID: {PRODUCTION_ID}")
    print("=" * 60)

    ensure_production()

    success = 0
    for scene_id, idx in SCENES:
        try:
            sync_scene(scene_id, idx)
            success += 1
        except Exception as e:
            print(f"  ERROR on {scene_id}: {e}")

    print("\n" + "=" * 60)
    print(f"Done: {success}/{len(SCENES)} scenes synced")
    print(f"Dashboard production ID: {PRODUCTION_ID}")
    print("=" * 60)

if __name__ == "__main__":
    main()
