"""Tests for format-specific template sections in cinematic director and cinematographer skills.

Validates that the skill files contain the required format mode sections, scale hierarchies,
anti-pattern blocks, self-critique loop, character anchor protocol, and transition motion support.
"""

import re
from pathlib import Path

import pytest

# Paths to skill files (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
CINEMATIC_DIRECTOR_PATH = PROJECT_ROOT / "shared" / "skills" / "cinematic-director" / "SKILL.md"
CINEMATOGRAPHER_PATH = PROJECT_ROOT / "shared" / "skills" / "cinematographer" / "SKILL.md"


@pytest.fixture
def cinematic_director_content():
    """Read the cinematic director SKILL.md content."""
    assert CINEMATIC_DIRECTOR_PATH.exists(), f"Cinematic director skill not found at {CINEMATIC_DIRECTOR_PATH}"
    return CINEMATIC_DIRECTOR_PATH.read_text(encoding="utf-8")


@pytest.fixture
def cinematographer_content():
    """Read the cinematographer SKILL.md content."""
    assert CINEMATOGRAPHER_PATH.exists(), f"Cinematographer skill not found at {CINEMATOGRAPHER_PATH}"
    return CINEMATOGRAPHER_PATH.read_text(encoding="utf-8")


def _extract_section(content: str, heading: str) -> str:
    """Extract text from a heading until the next heading of same or higher level."""
    # Find heading line containing the search text
    lines = content.split("\n")
    start_idx = None
    level = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") and heading.lower() in stripped.lower():
            level = len(stripped) - len(stripped.lstrip("#"))
            start_idx = i + 1
            break

    if start_idx is None:
        return ""

    # Collect lines until next heading of same or higher level
    result_lines = []
    for i in range(start_idx, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            if heading_level <= level:
                break
        result_lines.append(lines[i])

    return "\n".join(result_lines)


class TestCinematicDirectorFormatModes:
    """Tests for format mode sections in cinematic director skill."""

    def test_cinematic_director_has_format_modes(self, cinematic_director_content):
        """Format Modes top-level section must exist."""
        assert "## Format Modes" in cinematic_director_content

    def test_has_vsl_format(self, cinematic_director_content):
        """VSL format section must exist."""
        assert "format: vsl" in cinematic_director_content.lower() or "### format: vsl" in cinematic_director_content.lower()

    def test_has_ad_format(self, cinematic_director_content):
        """Ad format section must exist."""
        assert "format: ad" in cinematic_director_content.lower()

    def test_has_ugc_format(self, cinematic_director_content):
        """UGC format section must exist."""
        assert "format: ugc" in cinematic_director_content.lower()

    def test_ad_format_has_3_level_hierarchy(self, cinematic_director_content):
        """Ad format must specify 3-level scale hierarchy: EPIC, PRODUCT, INTIMATE."""
        ad_section = _extract_section(cinematic_director_content, "format: ad")
        assert ad_section, "Ad format section not found"
        assert "EPIC" in ad_section
        assert "PRODUCT" in ad_section
        assert "INTIMATE" in ad_section

    def test_ugc_format_defaults_intimate(self, cinematic_director_content):
        """UGC format must default to INTIMATE scale."""
        ugc_section = _extract_section(cinematic_director_content, "format: ugc")
        assert ugc_section, "UGC format section not found"
        assert "INTIMATE" in ugc_section
        # Check it's described as default
        assert "default" in ugc_section.lower()

    def test_ad_has_do_not_section(self, cinematic_director_content):
        """Ad format must have a DO NOT anti-pattern section."""
        ad_section = _extract_section(cinematic_director_content, "format: ad")
        assert ad_section, "Ad format section not found"
        assert "DO NOT" in ad_section

    def test_ugc_has_do_not_section(self, cinematic_director_content):
        """UGC format must have a DO NOT anti-pattern section."""
        ugc_section = _extract_section(cinematic_director_content, "format: ugc")
        assert ugc_section, "UGC format section not found"
        assert "DO NOT" in ugc_section

    def test_ad_scene_limit(self, cinematic_director_content):
        """Ad format must specify 8-12 scene limit."""
        ad_section = _extract_section(cinematic_director_content, "format: ad")
        assert ad_section, "Ad format section not found"
        assert "8-12" in ad_section or "max 8" in ad_section.lower() or "max 12" in ad_section.lower()

    def test_ugc_scene_limit(self, cinematic_director_content):
        """UGC format must specify 4-6 scene limit."""
        ugc_section = _extract_section(cinematic_director_content, "format: ugc")
        assert ugc_section, "UGC format section not found"
        assert "4-6" in ugc_section or "max 4" in ugc_section.lower() or "max 6" in ugc_section.lower()

    def test_no_consecutive_same_scale(self, cinematic_director_content):
        """Ad format must specify no consecutive same-scale constraint."""
        ad_section = _extract_section(cinematic_director_content, "format: ad")
        assert ad_section, "Ad format section not found"
        has_constraint = (
            "consecutive" in ad_section.lower()
            or "adjacent" in ad_section.lower()
        )
        assert has_constraint, "Ad section must mention consecutive/adjacent scale constraint"

    def test_cinematic_director_all_formats(self, cinematic_director_content):
        """All three format sections must be present and non-empty."""
        for fmt in ["format: vsl", "format: ad", "format: ugc"]:
            section = _extract_section(cinematic_director_content, fmt)
            assert section, f"Section '{fmt}' not found"
            assert len(section.strip()) > 50, f"Section '{fmt}' is too short to be meaningful"


class TestSelfCritiqueAndProtocols:
    """Tests for self-critique loop, character anchor, and compliance sections."""

    def test_self_critique_loop_exists(self, cinematic_director_content):
        """Self-Critique Loop section must exist."""
        assert "Self-Critique Loop" in cinematic_director_content

    def test_self_critique_references_lessons_learned(self, cinematic_director_content):
        """Self-critique loop must reference lessons_learned.json."""
        critique_section = _extract_section(cinematic_director_content, "Self-Critique Loop")
        assert critique_section, "Self-Critique Loop section not found"
        assert "lessons_learned" in critique_section or "lessons-learned" in critique_section.lower()

    def test_character_anchor_protocol_exists(self, cinematic_director_content):
        """Character Anchor Protocol section must exist."""
        assert "Character Anchor Protocol" in cinematic_director_content

    def test_character_anchor_describes_embedding(self, cinematic_director_content):
        """Character anchor protocol must describe embedding anchor in every scene prompt."""
        anchor_section = _extract_section(cinematic_director_content, "Character Anchor Protocol")
        assert anchor_section, "Character Anchor Protocol section not found"
        assert "every scene" in anchor_section.lower() or "every scene prompt" in anchor_section.lower()

    def test_compliance_enforcement_90_threshold(self, cinematic_director_content):
        """Compliance enforcement must specify 90+ threshold."""
        compliance_section = _extract_section(cinematic_director_content, "Compliance Enforcement")
        assert compliance_section, "Compliance Enforcement section not found"
        assert "90" in compliance_section


class TestTransitions:
    """Tests for transition point identification and caps."""

    def test_transition_point_identification_exists(self, cinematic_director_content):
        """Transition Point Identification section must exist."""
        assert "Transition Point Identification" in cinematic_director_content

    def test_transition_caps_per_format(self, cinematic_director_content):
        """Transition caps must be documented for each format."""
        transition_section = _extract_section(cinematic_director_content, "Transition Point Identification")
        assert transition_section, "Transition Point Identification section not found"
        # Check all format caps are mentioned
        assert "vsl" in transition_section.lower() or "VSL" in transition_section
        assert "ad" in transition_section.lower() or "Ad" in transition_section
        assert "ugc" in transition_section.lower() or "UGC" in transition_section

    def test_transition_types_documented(self, cinematic_director_content):
        """Transition types (morph, dissolve, zoom) must be documented."""
        transition_section = _extract_section(cinematic_director_content, "Transition Point Identification")
        assert transition_section, "Transition Point Identification section not found"
        assert "morph" in transition_section.lower()
        assert "dissolve" in transition_section.lower()
        assert "zoom" in transition_section.lower()


class TestCinematographerTransitionMotion:
    """Tests for transition_motion support in cinematographer skill."""

    def test_cinematographer_transition_motion(self, cinematographer_content):
        """Cinematographer must have transition_motion field documented."""
        assert "transition_motion" in cinematographer_content

    def test_transition_motion_section_exists(self, cinematographer_content):
        """Transition Motion Specification section must exist."""
        assert "Transition Motion Specification" in cinematographer_content

    def test_transition_motion_values_documented(self, cinematographer_content):
        """Available transition motion values must be documented."""
        section = _extract_section(cinematographer_content, "Transition Motion Specification")
        assert section, "Transition Motion Specification section not found"
        assert "slow_dissolve_zoom_in" in section
        assert "static_morph" in section

    def test_transition_duration_override(self, cinematographer_content):
        """Transition scenes must specify duration: 10."""
        section = _extract_section(cinematographer_content, "Transition Motion")
        assert section, "Transition Motion section not found"
        assert "10" in section
        assert "duration" in section.lower()
