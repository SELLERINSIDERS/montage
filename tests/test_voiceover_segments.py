"""Tests for per-scene voiceover generation and Whisper transcription."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Voiceover segment generation tests
# ---------------------------------------------------------------------------


class TestGenerateSegment:
    """Test generate_segment() per-format voice selection."""

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_vsl_uses_laura_voice(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_segment

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"fake_audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_segment("scene_01", "Hello world", "vsl", tmpdir, client=mock_client)

        mock_client.text_to_speech.convert.assert_called_once()
        call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs["voice_id"] == "FGY2WhTYpPnrIDTdsKH5"
        assert call_kwargs.kwargs["voice_settings"]["speed"] == 1.3
        assert result["voice"] == "Laura"

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_ad_uses_sarah_voice(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_segment

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"fake_audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_segment("scene_01", "Ad text", "ad", tmpdir, client=mock_client)

        call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs["voice_id"] == "EXAVITQu4vr4xnSDxMaL"
        assert call_kwargs.kwargs["voice_settings"]["speed"] == 1.1
        assert result["voice"] == "Sarah"

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_ugc_uses_jessica_voice(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_segment

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"fake_audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_segment("scene_01", "UGC text", "ugc", tmpdir, client=mock_client)

        call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs["voice_id"] == "cgSgspJ2msm6clMCkdW9"
        assert call_kwargs.kwargs["voice_settings"]["speed"] == 1.0
        assert result["voice"] == "Jessica"

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_output_saved_to_correct_path(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_segment

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"fake_audio_data"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_segment("scene_05", "Test text", "vsl", tmpdir, client=mock_client)

        assert result["scene_id"] == "scene_05"
        assert result["path"].endswith("scene_05_vo.mp3")
        assert result["chars"] == len("Test text")

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_audio_bytes_written_to_file(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_segment

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"chunk1", b"chunk2"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_segment("scene_01", "Hello", "vsl", tmpdir, client=mock_client)
            with open(result["path"], "rb") as f:
                assert f.read() == b"chunk1chunk2"


class TestGenerateAllSegments:
    """Test generate_all_segments() master script parsing and batch generation."""

    def _setup_project(self, tmpdir):
        """Create minimal project structure for testing."""
        project_dir = Path(tmpdir) / "test_project"
        copy_dir = project_dir / "copy"
        manifest_dir = project_dir / "manifest"
        segments_dir = project_dir / "audio" / "segments"
        copy_dir.mkdir(parents=True)
        manifest_dir.mkdir(parents=True)
        segments_dir.mkdir(parents=True)

        # Compliance gate fixtures (required by generate_all_segments compliance check)
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "PASS"})
        )
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 95})
        )

        # Master script with scene markers
        master_script = """# Scene 1
This is the narration for scene one.

# Scene 2
Scene two has different text.

# Scene 3
Silent scene.
"""
        (copy_dir / "master_script.md").write_text(master_script)

        # Audio design with scene configs
        audio_design = {
            "scenes": [
                {"scene_id": "scene_01", "type": "narrated", "narration": "This is the narration for scene one."},
                {"scene_id": "scene_02", "type": "narrated", "narration": "Scene two has different text."},
                {"scene_id": "scene_03", "type": "silent", "narration": ""},
            ]
        }
        (manifest_dir / "audio_design.json").write_text(json.dumps(audio_design))

        return str(project_dir)

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_generates_one_segment_per_narrated_scene(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_all_segments

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            results = generate_all_segments(
                audio_design_path=os.path.join(project_dir, "manifest", "audio_design.json"),
                project_dir=project_dir,
                format="vsl",
                client=mock_client,
            )

        # scene_03 is silent, should be skipped
        assert len(results) == 2
        assert results[0]["scene_id"] == "scene_01"
        assert results[1]["scene_id"] == "scene_02"

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_skips_silent_scenes(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_all_segments

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            results = generate_all_segments(
                audio_design_path=os.path.join(project_dir, "manifest", "audio_design.json"),
                project_dir=project_dir,
                format="vsl",
                client=mock_client,
            )

        scene_ids = [r["scene_id"] for r in results]
        assert "scene_03" not in scene_ids

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_tracks_character_count(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_all_segments

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"audio"]

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            results = generate_all_segments(
                audio_design_path=os.path.join(project_dir, "manifest", "audio_design.json"),
                project_dir=project_dir,
                format="vsl",
                client=mock_client,
            )

        total_chars = sum(r["chars"] for r in results)
        assert total_chars > 0

    @patch("scripts.generate_voiceover_segments.ElevenLabs")
    def test_increments_manifest_api_usage(self, MockElevenLabs):
        from scripts.generate_voiceover_segments import generate_all_segments

        mock_client = MockElevenLabs.return_value
        mock_client.text_to_speech.convert.return_value = [b"audio"]

        mock_manifest = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            results = generate_all_segments(
                audio_design_path=os.path.join(project_dir, "manifest", "audio_design.json"),
                project_dir=project_dir,
                format="vsl",
                client=mock_client,
                manifest=mock_manifest,
            )

        # Should be called for each narrated scene (2 scenes)
        chars_calls = [c for c in mock_manifest.increment_api_usage.call_args_list if c.args[0] == "elevenlabs_chars"]
        calls_calls = [c for c in mock_manifest.increment_api_usage.call_args_list if c.args[0] == "elevenlabs_calls"]
        assert len(chars_calls) == 2
        assert len(calls_calls) == 2
        # Each elevenlabs_calls increment should be 1
        for c in calls_calls:
            assert c.args[1] == 1


# ---------------------------------------------------------------------------
# Whisper transcription tests
# ---------------------------------------------------------------------------


class TestTranscribeSegment:
    """Test transcribe_segment() word-level output."""

    @patch("scripts.transcribe_segments.whisper")
    def test_returns_text_and_words(self, mock_whisper):
        from scripts.transcribe_segments import transcribe_segment

        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 1.5,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.7},
                        {"word": "world", "start": 0.8, "end": 1.5},
                    ],
                }
            ],
        }

        result = transcribe_segment("/fake/audio.mp3", model=mock_model)
        assert result["text"] == "Hello world"
        assert len(result["words"]) == 2
        assert result["words"][0]["word"] == "Hello"
        assert "start" in result["words"][0]
        assert "end" in result["words"][0]

    @patch("scripts.transcribe_segments.whisper")
    def test_word_entries_have_required_keys(self, mock_whisper):
        from scripts.transcribe_segments import transcribe_segment

        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Test",
            "segments": [
                {
                    "text": "Test",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [{"word": "Test", "start": 0.0, "end": 0.5}],
                }
            ],
        }

        result = transcribe_segment("/fake/audio.mp3", model=mock_model)
        for word in result["words"]:
            assert "word" in word
            assert "start" in word
            assert "end" in word


class TestTranscribeAllSegments:
    """Test transcribe_all_segments() batch processing."""

    @patch("scripts.transcribe_segments.whisper")
    def test_processes_all_mp3_files(self, mock_whisper):
        from scripts.transcribe_segments import transcribe_all_segments

        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Hello",
            "segments": [
                {
                    "text": "Hello",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [{"word": "Hello", "start": 0.0, "end": 0.5}],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake mp3 files
            (Path(tmpdir) / "scene_01_vo.mp3").write_bytes(b"fake")
            (Path(tmpdir) / "scene_02_vo.mp3").write_bytes(b"fake")
            (Path(tmpdir) / "other_file.txt").write_text("not audio")

            results = transcribe_all_segments(tmpdir, model_size="base")

        assert len(results) == 2
        scene_ids = sorted([r["scene_id"] for r in results])
        assert scene_ids == ["scene_01", "scene_02"]

    @patch("scripts.transcribe_segments.whisper")
    def test_saves_json_alongside_mp3(self, mock_whisper):
        from scripts.transcribe_segments import transcribe_all_segments

        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Hello",
            "segments": [
                {
                    "text": "Hello",
                    "start": 0.0,
                    "end": 0.5,
                    "words": [{"word": "Hello", "start": 0.0, "end": 0.5}],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "scene_01_vo.mp3").write_bytes(b"fake")

            transcribe_all_segments(tmpdir, model_size="base")

            json_path = Path(tmpdir) / "scene_01_vo.json"
            assert json_path.exists()
            data = json.loads(json_path.read_text())
            assert "text" in data
            assert "words" in data
