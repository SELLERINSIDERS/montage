"""Tests for merge_whisper.py — merges per-scene Whisper JSONs with time offsets."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_whisper_json(segments, path):
    """Write a Whisper-format JSON file."""
    path.write_text(json.dumps({"segments": segments}))


@pytest.fixture
def project_dir(tmp_path):
    """Project with 3 scenes, each having MP3 + JSON segments."""
    segments_dir = tmp_path / "audio" / "segments"
    segments_dir.mkdir(parents=True)

    # Scene 01: 2.5s duration, one segment
    (segments_dir / "scene_01_vo.mp3").write_bytes(b"\xff" * 10)
    _make_whisper_json(
        [{"start": 0.0, "end": 2.3, "text": "Hello world"}],
        segments_dir / "scene_01_vo.json",
    )

    # Scene 02: 3.0s duration, one segment with words
    (segments_dir / "scene_02_vo.mp3").write_bytes(b"\xff" * 10)
    _make_whisper_json(
        [
            {
                "start": 0.0,
                "end": 2.8,
                "text": "Second scene",
                "words": [
                    {"word": "Second", "start": 0.0, "end": 1.2},
                    {"word": "scene", "start": 1.3, "end": 2.8},
                ],
            }
        ],
        segments_dir / "scene_02_vo.json",
    )

    # Scene 03: 1.5s duration, one segment
    (segments_dir / "scene_03_vo.mp3").write_bytes(b"\xff" * 10)
    _make_whisper_json(
        [{"start": 0.0, "end": 1.2, "text": "End"}],
        segments_dir / "scene_03_vo.json",
    )

    return tmp_path


class TestTimestampOffsets:
    """Timestamps shifted by cumulative audio duration."""

    @patch("scripts.merge_whisper._get_audio_duration")
    def test_cumulative_offsets_applied(self, mock_duration, project_dir):
        from scripts.merge_whisper import merge_whisper

        # Scene 01 = 2.5s, Scene 02 = 3.0s, Scene 03 = 1.5s
        mock_duration.side_effect = [2.5, 3.0, 1.5]

        result = merge_whisper(str(project_dir))

        segs = result["segments"]
        assert len(segs) == 3

        # Scene 01: offset=0
        assert segs[0]["start"] == 0.0
        assert segs[0]["end"] == 2.3

        # Scene 02: offset=2.5
        assert segs[1]["start"] == 2.5
        assert segs[1]["end"] == pytest.approx(5.3, abs=0.01)

        # Scene 03: offset=2.5+3.0=5.5
        assert segs[2]["start"] == 5.5
        assert segs[2]["end"] == pytest.approx(6.7, abs=0.01)


class TestSceneIdDerivation:
    """scene_id derived correctly from filenames."""

    @patch("scripts.merge_whisper._get_audio_duration")
    def test_scene_id_from_filename(self, mock_duration, project_dir):
        from scripts.merge_whisper import merge_whisper

        mock_duration.side_effect = [2.5, 3.0, 1.5]

        result = merge_whisper(str(project_dir))
        segs = result["segments"]

        assert segs[0]["scene_id"] == "scene_01"
        assert segs[1]["scene_id"] == "scene_02"
        assert segs[2]["scene_id"] == "scene_03"


class TestWordTimestamps:
    """Word-level timestamps shifted when present."""

    @patch("scripts.merge_whisper._get_audio_duration")
    def test_words_shifted_by_offset(self, mock_duration, project_dir):
        from scripts.merge_whisper import merge_whisper

        mock_duration.side_effect = [2.5, 3.0, 1.5]

        result = merge_whisper(str(project_dir))
        segs = result["segments"]

        # Scene 02 (index 1) has words, offset = 2.5
        assert "words" in segs[1]
        words = segs[1]["words"]
        assert words[0]["start"] == 2.5
        assert words[0]["end"] == pytest.approx(3.7, abs=0.01)
        assert words[1]["start"] == pytest.approx(3.8, abs=0.01)
        assert words[1]["end"] == pytest.approx(5.3, abs=0.01)


class TestFallbackDuration:
    """Fallback to segment end time when MP3 missing."""

    def test_uses_last_segment_end_when_no_mp3(self, tmp_path):
        from scripts.merge_whisper import merge_whisper

        segments_dir = tmp_path / "audio" / "segments"
        segments_dir.mkdir(parents=True)

        # Only JSON, no MP3
        _make_whisper_json(
            [{"start": 0.0, "end": 2.3, "text": "Hello"}],
            segments_dir / "scene_01_vo.json",
        )
        _make_whisper_json(
            [{"start": 0.0, "end": 1.5, "text": "World"}],
            segments_dir / "scene_02_vo.json",
        )

        result = merge_whisper(str(tmp_path))
        segs = result["segments"]

        # Scene 01 falls back to end=2.3 as duration
        # Scene 02 offset = 2.3
        assert segs[1]["start"] == 2.3
        assert segs[1]["end"] == pytest.approx(3.8, abs=0.01)


class TestMergeWhisperEmpty:
    """FileNotFoundError on empty directory."""

    def test_raises_on_no_json_segments(self, tmp_path):
        from scripts.merge_whisper import merge_whisper

        (tmp_path / "audio" / "segments").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="No Whisper JSON segments"):
            merge_whisper(str(tmp_path))

    def test_raises_on_missing_segments_dir(self, tmp_path):
        from scripts.merge_whisper import merge_whisper

        with pytest.raises(FileNotFoundError, match="No Whisper JSON segments"):
            merge_whisper(str(tmp_path))
