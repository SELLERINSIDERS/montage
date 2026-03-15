"""Image+motion_prompt hash-based clip generation dedup cache.

Tracks which Kling clips have already been generated, enabling batch scripts
to skip redundant video generation. Uses prompt_hash with image_bytes for
content-aware cache keys (regenerates if either prompt or source image changes).

Usage:
    from video.kling.clip_cache import ClipCache

    cache = ClipCache(Path("vsl/example-project"))
    existing = cache.has_cached("scene_01", "Camera slowly pushes in...", "images/v1/scene_01.png")
    if existing:
        print(f"Already generated: {existing}")
    else:
        # generate clip...
        cache.record("scene_01", "Camera slowly pushes in...", "images/v1/scene_01.png", "video/clips/scene_01.mp4")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from video.kling.prompt_hash import prompt_hash


class ClipCache:
    """Track Kling clip generation by image+motion_prompt hash to skip regeneration."""

    def __init__(self, project_dir: Path):
        self.cache_file = project_dir / "video" / "clips" / "cache.json"
        self._cache = self._load()

    def _load(self) -> dict:
        if self.cache_file.exists():
            return json.loads(self.cache_file.read_text())
        return {}

    def _save(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self._cache, indent=2))

    def has_cached(self, scene_id: str, motion_prompt: str, image_path: str) -> Optional[str]:
        """Return cached clip path if image+prompt hash matches, else None."""
        image_bytes = Path(image_path).read_bytes() if Path(image_path).exists() else b""
        key = prompt_hash(motion_prompt, image_bytes)
        entry = self._cache.get(scene_id)
        if entry and entry.get("hash") == key and Path(entry["path"]).exists():
            return entry["path"]
        return None

    def record(self, scene_id: str, motion_prompt: str, image_path: str, clip_path: str):
        """Record generated clip with its content hash."""
        image_bytes = Path(image_path).read_bytes() if Path(image_path).exists() else b""
        self._cache[scene_id] = {
            "hash": prompt_hash(motion_prompt, image_bytes),
            "path": clip_path,
            "generated_at": datetime.utcnow().isoformat(),
        }
        self._save()
