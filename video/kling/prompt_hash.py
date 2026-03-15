"""Deterministic prompt hashing for cache dedup.

Generates a stable 16-character hex hash from prompt text and optional image
content. Used for image generation dedup (skip if prompt unchanged) and Kling
clip dedup (skip if image+prompt unchanged).

Usage:
    from video.kling.prompt_hash import prompt_hash

    h = prompt_hash("A sweeping aerial shot of ancient Alexandria...")
    # -> "a3f2b1c4d5e6f7a8"

    h = prompt_hash("Same prompt", image_bytes=raw_png_bytes)
    # -> "b4e3c2d1f0a9e8b7"
"""

import hashlib


def prompt_hash(prompt: str, image_bytes: bytes = b"") -> str:
    """Generate deterministic hash for prompt + optional image content.

    Used for image generation dedup (skip if prompt unchanged) and
    Kling clip dedup (skip if image+prompt unchanged).

    Args:
        prompt: The text prompt to hash.
        image_bytes: Optional raw image bytes to include in hash.

    Returns:
        16-character hex string (first 64 bits of SHA-256).
    """
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    if image_bytes:
        h.update(image_bytes)
    return h.hexdigest()[:16]
