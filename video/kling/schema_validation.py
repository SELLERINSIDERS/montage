"""JSON schema definitions and validation for manifests and EDL.

Provides schema-based validation for the three core pipeline data formats:
- Kling manifest (scene array with prompt/image references)
- Audio design (scene-keyed SFX layer definitions)
- EDL (edit decision list for Remotion rendering)

Usage:
    from video.kling.schema_validation import validate_manifest, validate_edl

    validate_manifest(data)  # raises jsonschema.ValidationError on failure
"""

import re

import jsonschema


# ---------------------------------------------------------------------------
# Kling Manifest Schema
# ---------------------------------------------------------------------------

KLING_MANIFEST_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["scene", "name", "image", "prompt"],
        "properties": {
            "scene": {"type": "string"},
            "name": {"type": "string"},
            "image": {"type": "string"},
            "prompt": {"type": "string"},
            "duration": {"type": ["string", "number"]},
            "mode": {"type": "string"},
            "cfg_scale": {"type": "number"},
            "negative_prompt": {"type": "string"},
            "aspect_ratio": {"type": "string"},
        },
    },
}

# ---------------------------------------------------------------------------
# Audio Design Schema
# ---------------------------------------------------------------------------

AUDIO_DESIGN_SCHEMA = {
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "scenes": {
            "type": "object",
            "patternProperties": {
                "^scene_\\d+": {
                    "type": "object",
                    "required": ["name", "layers"],
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "layers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {
                                    "file": {"type": "string"},
                                    "volume": {"type": "number"},
                                    "loop": {"type": "boolean"},
                                    "delay_ms": {"type": "number"},
                                    "fadeIn_ms": {"type": "number"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# EDL Schema
# ---------------------------------------------------------------------------

EDL_SCHEMA = {
    "type": "object",
    "required": ["meta", "scenes"],
    "properties": {
        "meta": {
            "type": "object",
            "required": ["width", "height", "fps"],
            "properties": {
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "fps": {"type": "integer"},
                "version": {"type": "integer"},
                "total_duration_s": {"type": "number"},
            },
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "clip_src": {"type": "string"},
                    "duration_s": {"type": "number"},
                    "start_s": {"type": "number"},
                    "label": {"type": "string"},
                    "audio_type": {"type": "string"},
                },
            },
        },
        "voiceover": {
            "type": ["object", "null"],
            "properties": {
                "src": {"type": "string"},
                "whisper_data": {"type": "string"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_manifest(data):
    """Validate a Kling manifest (scene array) against the schema.

    Args:
        data: List of scene dicts from kling_manifest.json.

    Raises:
        jsonschema.ValidationError: If data does not conform to schema.
    """
    jsonschema.validate(instance=data, schema=KLING_MANIFEST_SCHEMA)


def validate_audio_design(data):
    """Validate audio_design.json against the schema.

    Args:
        data: Dict with 'scenes' key from audio_design.json.

    Raises:
        jsonschema.ValidationError: If data does not conform to schema.
    """
    jsonschema.validate(instance=data, schema=AUDIO_DESIGN_SCHEMA)


def validate_edl(data):
    """Validate an EDL JSON structure against the schema.

    Args:
        data: Dict with 'meta' and 'scenes' keys from edl.json.

    Raises:
        jsonschema.ValidationError: If data does not conform to schema.
    """
    jsonschema.validate(instance=data, schema=EDL_SCHEMA)


# ---------------------------------------------------------------------------
# Scene ID normalization
# ---------------------------------------------------------------------------

def normalize_scene_id(scene_id: str) -> str:
    """Normalize scene IDs to snake_case with letter suffix preserved.

    Handles all known formats:
      - PascalCase:  Scene01 -> scene_01, Scene04c -> scene_04c
      - Short form:  S04c -> scene_04c, S04 -> scene_04
      - No separator: scene01 -> scene_01, scene04c -> scene_04c
      - Already normalized: scene_04c -> scene_04c (unchanged)
    """
    # Long forms: Scene01, Scene_04c, scene-04, scene04c, scene_04c
    m = re.match(r'[Ss]cene[_-]?(\d+)([a-zA-Z]?)', scene_id)
    if m:
        suffix = m.group(2).lower()
        return f"scene_{m.group(1).zfill(2)}{suffix}"
    # Short form: S04c, S04, s12b
    m = re.match(r'[Ss](\d+)([a-zA-Z]?)$', scene_id)
    if m:
        suffix = m.group(2).lower()
        return f"scene_{m.group(1).zfill(2)}{suffix}"
    return scene_id.lower()
