"""Prompt-hash-based image generation dedup cache.

Tracks which scene prompts have already been generated, enabling batch scripts
to skip redundant image generation. Uses prompt_hash for deterministic cache keys.

Usage:
    from video.kling.image_cache import ImageCache

    cache = ImageCache(Path("vsl/cleopatra"))
    existing = cache.has_cached("scene_01", "A sweeping aerial shot...")
    if existing:
        print(f"Already generated: {existing}")
    else:
        # generate image...
        cache.record("scene_01", "A sweeping aerial shot...", "images/v1/scene_01.png")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from video.kling.prompt_hash import prompt_hash


class ImageCache:
    """Track image generation by prompt hash to skip regeneration."""

    def __init__(self, project_dir: Path):
        self.cache_file = project_dir / "images" / "metadata.json"
        self._cache = self._load()

    def _load(self) -> dict:
        if self.cache_file.exists():
            return json.loads(self.cache_file.read_text())
        return {}

    def _save(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self._cache, indent=2))

    def has_cached(self, scene_id: str, prompt: str) -> Optional[str]:
        """Return cached image path if prompt hash matches, else None."""
        key = prompt_hash(prompt)
        entry = self._cache.get(scene_id)
        if entry and entry.get("hash") == key and Path(entry["path"]).exists():
            return entry["path"]
        return None

    def record(self, scene_id: str, prompt: str, image_path: str):
        """Record generated image with its prompt hash."""
        self._cache[scene_id] = {
            "hash": prompt_hash(prompt),
            "path": image_path,
            "generated_at": datetime.utcnow().isoformat(),
        }
        self._save()
