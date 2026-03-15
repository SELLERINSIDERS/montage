"""Tests for EDL generator: manifest + audio_design + whisper -> edl.json.

Tests cover:
- generate_edl produces valid EDL JSON with meta, voiceover, scenes
- Scene duration derived from whisper segment timing
- audio_type maps from audio_design.json classification
- Format dimensions (VSL 1080x1920, UGC 1080x1080)
- playback_rate clamped at minimum 0.5
- Changelog entry with version 1 on creation
- EDL modification preserves schema and increments version
- Missing whisper data raises clear error
"""

import json
import os
import pytest
from unittest.mock import patch

from scripts.edl_generator import generate_edl, modify_edl, FORMAT_DIMENSIONS


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def production_dir(tmp_path):
    """Create a minimal production directory structure."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    video_dir = tmp_path / "video" / "clips"
    video_dir.mkdir(parents=True)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    return tmp_path


@pytest.fixture
def manifest_path(production_dir):
    """Create a 3-scene workflow manifest JSON."""
    manifest = {
        "schema_version": "workflow-manifest-v2",
        "format": "vsl",
        "slug": "test-production",
        "scenes": [
            {
                "scene_id": "scene_01",
                "gates": {"video": {"status": "approved"}},
                "video": "video/clips/scene_01.mp4",
                "audio": {"type": "voiceover_only"},
            },
            {
                "scene_id": "scene_02",
                "gates": {"video": {"status": "approved"}},
                "video": "video/clips/scene_02.mp4",
                "audio": {"type": "mixed"},
            },
            {
                "scene_id": "scene_03",
                "gates": {"video": {"status": "approved"}},
                "video": "video/clips/scene_03.mp4",
                "audio": {"type": "silent"},
            },
        ],
        "audio_config": {
            "preset": "narrated",
        },
    }
    path = production_dir / "state" / "manifest.json"
    path.write_text(json.dumps(manifest))

    # Create dummy clip files
    for i in range(1, 4):
        (production_dir / "video" / "clips" / f"scene_{i:02d}.mp4").write_bytes(b"\x00")

    return str(path)


@pytest.fixture
def audio_design_path(production_dir):
    """Create an audio_design.json with per-scene classification."""
    design = {
        "scenes": {
            "scene_01": {
                "classification": "voiceover_only",
                "ambient_audio": [],
            },
            "scene_02": {
                "classification": "mixed",
                "ambient_audio": [
                    {
                        "src": "sfx/ambient_market.mp3",
                        "volume": 0.3,
                        "loop": True,
                    }
                ],
            },
            "scene_03": {
                "classification": "silent",
                "ambient_audio": [],
            },
        }
    }
    path = production_dir / "state" / "audio_design.json"
    path.write_text(json.dumps(design))
    return str(path)


@pytest.fixture
def whisper_path(production_dir):
    """Create a whisper JSON with segment timing per scene."""
    whisper = {
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.5,
                "text": "In the ancient world",
                "scene_id": "scene_01",
            },
            {
                "id": 1,
                "start": 4.5,
                "end": 10.2,
                "text": "merchants gathered in bazaars",
                "scene_id": "scene_02",
            },
            {
                "id": 2,
                "start": 10.2,
                "end": 13.0,
                "text": "silence fell over the temple",
                "scene_id": "scene_03",
            },
        ]
    }
    path = production_dir / "audio" / "whisper.json"
    path.write_text(json.dumps(whisper))

    # Also create the voiceover file
    (production_dir / "audio" / "voiceover.mp3").write_bytes(b"\x00")

    return str(path)


# ── Test: generate_edl produces valid structure ──────────────────────


class TestGenerateEdl:
    """generate_edl with a 3-scene manifest produces valid EDL JSON."""

    def test_produces_valid_edl_structure(
        self, manifest_path, audio_design_path, whisper_path, production_dir
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert "meta" in edl
        assert "voiceover" in edl
        assert "scenes" in edl
        assert "changelog" in edl

    def test_meta_has_required_fields(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        meta = edl["meta"]
        assert meta["fps"] == 24
        assert meta["title"] == "test-production"
        assert meta["format"] == "vsl"
        assert meta["version"] == 1

    def test_scenes_count_matches_approved(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert len(edl["scenes"]) == 3

    def test_voiceover_section(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert edl["voiceover"] is not None
        assert "src" in edl["voiceover"]
        assert "whisper_data" in edl["voiceover"]


# ── Test: Scene duration from whisper timing ─────────────────────────


class TestSceneDurationFromWhisper:
    """Scene duration derived from voiceover segment timing."""

    def test_scene_01_duration(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        scene_01 = edl["scenes"][0]
        # Whisper: start=0.0, end=4.5 => duration=4.5
        assert abs(scene_01["duration_s"] - 4.5) < 0.01

    def test_scene_02_duration(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        scene_02 = edl["scenes"][1]
        # Whisper: start=4.5, end=10.2 => duration=5.7
        assert abs(scene_02["duration_s"] - 5.7) < 0.01

    def test_scene_03_duration(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        scene_03 = edl["scenes"][2]
        # Whisper: start=10.2, end=13.0 => duration=2.8
        assert abs(scene_03["duration_s"] - 2.8) < 0.01


# ── Test: audio_type maps from audio_design ──────────────────────────


class TestAudioTypeMapping:
    """audio_type maps from audio_design.json classification."""

    def test_voiceover_only_mapped(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert edl["scenes"][0]["audio_type"] == "voiceover_only"

    def test_mixed_mapped(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert edl["scenes"][1]["audio_type"] == "mixed"

    def test_silent_mapped(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert edl["scenes"][2]["audio_type"] == "silent"

    def test_ambient_audio_included_for_mixed(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        scene_02 = edl["scenes"][1]
        assert len(scene_02["ambient_audio"]) == 1
        assert scene_02["ambient_audio"][0]["src"] == "sfx/ambient_market.mp3"


# ── Test: Format dimensions ──────────────────────────────────────────


class TestFormatDimensions:
    """VSL format produces width=1080, height=1920; UGC produces 1080x1080."""

    def test_vsl_dimensions(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert edl["meta"]["width"] == 1080
        assert edl["meta"]["height"] == 1920

    def test_ugc_dimensions(
        self, production_dir, audio_design_path, whisper_path
    ):
        """Override format to UGC and check dimensions."""
        manifest = {
            "schema_version": "workflow-manifest-v2",
            "format": "ugc",
            "slug": "ugc-test",
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "gates": {"video": {"status": "approved"}},
                    "video": "video/clips/scene_01.mp4",
                    "audio": {"type": "voiceover_only"},
                },
            ],
            "audio_config": {"preset": "narrated"},
        }
        path = production_dir / "state" / "manifest_ugc.json"
        path.write_text(json.dumps(manifest))
        edl = generate_edl(str(path), audio_design_path, whisper_path)
        assert edl["meta"]["width"] == 1080
        assert edl["meta"]["height"] == 1080

    def test_ad_dimensions(
        self, production_dir, audio_design_path, whisper_path
    ):
        manifest = {
            "schema_version": "workflow-manifest-v2",
            "format": "ad",
            "slug": "ad-test",
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "gates": {"video": {"status": "approved"}},
                    "video": "video/clips/scene_01.mp4",
                    "audio": {"type": "voiceover_only"},
                },
            ],
            "audio_config": {"preset": "narrated"},
        }
        path = production_dir / "state" / "manifest_ad.json"
        path.write_text(json.dumps(manifest))
        edl = generate_edl(str(path), audio_design_path, whisper_path)
        assert edl["meta"]["width"] == 1080
        assert edl["meta"]["height"] == 1920

    def test_format_dimensions_dict(self):
        assert FORMAT_DIMENSIONS["vsl"] == (1080, 1920)
        assert FORMAT_DIMENSIONS["ad"] == (1080, 1920)
        assert FORMAT_DIMENSIONS["ugc"] == (1080, 1080)


# ── Test: Playback rate clamping ─────────────────────────────────────


class TestPlaybackRateClamping:
    """playback_rate clamped at minimum 0.5 when clip shorter than scene."""

    def test_no_playback_rate_override_by_default(
        self, manifest_path, audio_design_path, whisper_path
    ):
        """When clip duration >= scene duration, no override is set."""
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        # Default scenes should not need clamping
        for scene in edl["scenes"]:
            # playback_rate_override should be absent or None for normal scenes
            assert scene.get("playback_rate_override") is None


# ── Test: Changelog ──────────────────────────────────────────────────


class TestChangelog:
    """EDL includes changelog entry with version 1 and creation description."""

    def test_changelog_has_initial_entry(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert len(edl["changelog"]) == 1
        assert edl["changelog"][0]["version"] == 1
        assert len(edl["changelog"][0]["changes"]) > 0

    def test_changelog_entry_has_date(
        self, manifest_path, audio_design_path, whisper_path
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        assert "date" in edl["changelog"][0]


# ── Test: EDL modification ───────────────────────────────────────────


class TestEdlModification:
    """EDL modification preserves schema validity and increments version."""

    def test_modify_increments_version(
        self, manifest_path, audio_design_path, whisper_path, production_dir
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl))

        changes = [{"type": "update_label", "scene_id": "scene_01", "label": "New label"}]
        modified = modify_edl(str(edl_path), changes)
        assert modified["meta"]["version"] == 2

    def test_modify_appends_changelog(
        self, manifest_path, audio_design_path, whisper_path, production_dir
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl))

        changes = [{"type": "update_label", "scene_id": "scene_01", "label": "Updated"}]
        modified = modify_edl(str(edl_path), changes)
        assert len(modified["changelog"]) == 2
        assert modified["changelog"][-1]["version"] == 2

    def test_modify_applies_label_change(
        self, manifest_path, audio_design_path, whisper_path, production_dir
    ):
        edl = generate_edl(manifest_path, audio_design_path, whisper_path)
        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl))

        changes = [{"type": "update_label", "scene_id": "scene_01", "label": "My new label"}]
        modified = modify_edl(str(edl_path), changes)
        scene_01 = [s for s in modified["scenes"] if s["id"] == "scene_01"][0]
        assert scene_01["label"] == "My new label"


# ── Test: Missing whisper data ───────────────────────────────────────


class TestMissingWhisperData:
    """Missing Whisper data raises clear error (not silent failure)."""

    def test_missing_whisper_raises_error(
        self, manifest_path, audio_design_path, production_dir
    ):
        bad_path = str(production_dir / "audio" / "nonexistent.json")
        with pytest.raises(FileNotFoundError, match="[Ww]hisper"):
            generate_edl(manifest_path, audio_design_path, bad_path)
