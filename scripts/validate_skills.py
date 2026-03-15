"""Fail-fast skill validation for production startup.

Checks that all required shared skills (cinematic-director, cinematographer,
compliance-checker) resolve from known SKILL_ROOTS before any API calls are made.

Usage:
    from scripts.validate_skills import validate_skills
    validate_skills()  # raises RuntimeError if any skill is missing
"""

import os
from pathlib import Path


REQUIRED_SKILLS: list[str] = [
    "cinematic-director",
    "cinematographer",
    "compliance-checker",
]

SKILL_ROOTS: list[Path] = [
    Path("shared/skills"),
    Path(os.environ.get("SKILLS_DIR", "skills")),
]


def validate_skills() -> None:
    """Check all REQUIRED_SKILLS resolve from SKILL_ROOTS. Raise RuntimeError if any missing.

    Returns None on success. Raises RuntimeError listing every missing skill
    and the search paths that were checked.
    """
    missing: list[str] = []

    for skill in REQUIRED_SKILLS:
        found = False
        for root in SKILL_ROOTS:
            skill_file = root / skill / "SKILL.md"
            if skill_file.exists():
                found = True
                break
        if not found:
            missing.append(skill)

    if missing:
        search_paths = ", ".join(str(r) for r in SKILL_ROOTS)
        missing_names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required skills: {missing_names}. "
            f"Searched: {search_paths}"
        )

    return None
