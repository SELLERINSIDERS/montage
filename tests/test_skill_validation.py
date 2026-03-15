"""Tests for skill validation: fail-fast startup check for required skills."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from scripts.validate_skills import validate_skills, REQUIRED_SKILLS


class TestValidateSkillsPass:
    """When all required skills are present, validation succeeds silently."""

    def test_returns_none_when_all_skills_present(self, tmp_path):
        """validate_skills() returns None (no error) when every skill resolves."""
        # Create fake skill directories with SKILL.md
        for skill in REQUIRED_SKILLS:
            skill_dir = tmp_path / skill
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(f"# {skill}")

        with patch("scripts.validate_skills.SKILL_ROOTS", [tmp_path]):
            result = validate_skills()
            assert result is None


class TestValidateSkillsFail:
    """When skills are missing, validation raises RuntimeError."""

    def test_raises_runtime_error_on_missing_skill(self, tmp_path):
        """Missing skill triggers RuntimeError before any production work."""
        # Create only one of the required skills
        present = REQUIRED_SKILLS[0]
        skill_dir = tmp_path / present
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"# {present}")

        with patch("scripts.validate_skills.SKILL_ROOTS", [tmp_path]):
            with pytest.raises(RuntimeError) as exc_info:
                validate_skills()

            error_msg = str(exc_info.value)
            # All missing skills should be named in the error
            for skill in REQUIRED_SKILLS[1:]:
                assert skill in error_msg

    def test_error_includes_search_paths(self, tmp_path):
        """Error message lists where it looked so user can fix."""
        with patch("scripts.validate_skills.SKILL_ROOTS", [tmp_path]):
            with pytest.raises(RuntimeError) as exc_info:
                validate_skills()

            error_msg = str(exc_info.value)
            assert str(tmp_path) in error_msg

    def test_checks_cinematic_director(self, tmp_path):
        """cinematic-director is a required skill."""
        assert "cinematic-director" in REQUIRED_SKILLS

    def test_checks_cinematographer(self, tmp_path):
        """cinematographer is a required skill."""
        assert "cinematographer" in REQUIRED_SKILLS

    def test_checks_compliance_checker(self, tmp_path):
        """compliance-checker is a required skill."""
        assert "compliance-checker" in REQUIRED_SKILLS

    def test_all_missing_when_empty_roots(self, tmp_path):
        """When no skill roots have any skills, all are listed as missing."""
        with patch("scripts.validate_skills.SKILL_ROOTS", [tmp_path]):
            with pytest.raises(RuntimeError) as exc_info:
                validate_skills()

            error_msg = str(exc_info.value)
            for skill in REQUIRED_SKILLS:
                assert skill in error_msg
