"""Tests for prompt_hash deterministic hashing.

Validates:
- Same input produces same hash (deterministic)
- Different inputs produce different hashes
- Image bytes change the hash
- Output is 16-character hex string
"""

import pytest

from video.kling.prompt_hash import prompt_hash


class TestPromptHash:
    """prompt_hash produces deterministic, unique 16-char hex hashes."""

    def test_deterministic_same_input_same_hash(self):
        """Same prompt always returns same hash."""
        h1 = prompt_hash("A sweeping aerial shot of ancient Alexandria")
        h2 = prompt_hash("A sweeping aerial shot of ancient Alexandria")
        assert h1 == h2

    def test_different_prompts_different_hashes(self):
        """Different prompt text produces different hashes."""
        h1 = prompt_hash("A sweeping aerial shot")
        h2 = prompt_hash("A close-up of a golden chalice")
        assert h1 != h2

    def test_image_bytes_change_hash(self):
        """Adding image_bytes produces a different hash from text-only."""
        h_text = prompt_hash("Same prompt")
        h_with_image = prompt_hash("Same prompt", image_bytes=b"\x89PNG fake image data")
        assert h_text != h_with_image

    def test_output_is_16_char_hex(self):
        """Hash output is exactly 16 hex characters."""
        h = prompt_hash("Test prompt")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_prompt_still_produces_hash(self):
        """Even empty string produces valid hash."""
        h = prompt_hash("")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_image_bytes_different_hashes(self):
        """Same text but different images produce different hashes."""
        h1 = prompt_hash("Same text", image_bytes=b"image_a")
        h2 = prompt_hash("Same text", image_bytes=b"image_b")
        assert h1 != h2
