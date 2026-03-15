"""Tests for parity check logic.

Validates that check_parity() blocks Kling batch generation when:
- image count != expected scene count from manifest
- video prompt count != expected scene count
- all counts match (returns True)
"""

import json

import pytest

from video.kling.parity_check import ParityError, check_parity


class TestParityCheck:
    """check_parity validates image/prompt counts match expected scene count."""

    def _setup_project(self, tmp_path, num_scenes=3, num_images=3):
        """Create a minimal project structure with manifest and images."""
        # Create manifest
        manifest_dir = tmp_path / "manifest"
        manifest_dir.mkdir()
        scenes = [
            {
                "scene": f"{i:02d}",
                "name": f"scene_{i:02d}",
                "image": f"images/final/scene_{i:02d}.png",
                "prompt": f"A dramatic shot of scene {i}",
            }
            for i in range(1, num_scenes + 1)
        ]
        (manifest_dir / "kling_manifest.json").write_text(json.dumps(scenes))

        # Create images
        images_dir = tmp_path / "images" / "final"
        images_dir.mkdir(parents=True)
        for i in range(1, num_images + 1):
            (images_dir / f"scene_{i:02d}.png").write_bytes(b"\x89PNG fake")

        return tmp_path

    def test_raises_when_image_count_mismatch(self, tmp_path):
        """Fewer images than scenes raises ParityError."""
        self._setup_project(tmp_path, num_scenes=5, num_images=3)

        with pytest.raises(ParityError, match="image"):
            check_parity(tmp_path)

    def test_raises_when_more_images_than_scenes(self, tmp_path):
        """More images than scenes also raises ParityError."""
        self._setup_project(tmp_path, num_scenes=2, num_images=5)

        with pytest.raises(ParityError, match="image"):
            check_parity(tmp_path)

    def test_returns_true_when_counts_match(self, tmp_path):
        """Matching image and scene counts returns True."""
        self._setup_project(tmp_path, num_scenes=4, num_images=4)

        assert check_parity(tmp_path) is True

    def test_raises_when_manifest_missing(self, tmp_path):
        """Missing kling_manifest.json raises ParityError."""
        # No manifest directory at all
        images_dir = tmp_path / "images" / "final"
        images_dir.mkdir(parents=True)
        (images_dir / "scene_01.png").write_bytes(b"\x89PNG fake")

        with pytest.raises(ParityError, match="manifest"):
            check_parity(tmp_path)

    def test_falls_back_to_v1_images(self, tmp_path):
        """Uses images/v1/ when images/final/ is empty."""
        manifest_dir = tmp_path / "manifest"
        manifest_dir.mkdir()
        scenes = [
            {
                "scene": "01",
                "name": "scene_01",
                "image": "images/v1/scene_01.png",
                "prompt": "A shot",
            }
        ]
        (manifest_dir / "kling_manifest.json").write_text(json.dumps(scenes))

        # Create v1 images only (no final dir)
        v1_dir = tmp_path / "images" / "v1"
        v1_dir.mkdir(parents=True)
        (v1_dir / "scene_01.png").write_bytes(b"\x89PNG fake")

        assert check_parity(tmp_path) is True
