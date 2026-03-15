"""Compliance gate for voiceover generation.

Hard-blocks voiceover production if compliance_report.json is missing/failed
or panel_report.json score is below 90. This prevents wasted ElevenLabs API
credits on non-compliant scripts.

Usage:
    from video.kling.compliance_gate import check_compliance, ComplianceError

    try:
        check_compliance(Path("vsl/nightcap"))
    except ComplianceError as e:
        print(f"Blocked: {e}")
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ComplianceError(Exception):
    """Raised when compliance checks fail, blocking voiceover generation."""
    pass


def check_compliance(project_dir) -> bool:
    """Check compliance_report.json and panel_report.json before voiceover generation.

    Args:
        project_dir: Path to production directory (e.g., vsl/cleopatra/).

    Returns:
        True if all checks pass.

    Raises:
        ComplianceError: If any check fails with descriptive message.
    """
    project_dir = Path(project_dir)
    copy_dir = project_dir / "copy"

    # --- Check compliance_report.json ---
    compliance_path = copy_dir / "compliance_report.json"
    if not compliance_path.exists():
        raise ComplianceError(
            f"compliance_report.json not found at {compliance_path}. "
            "Run compliance check before voiceover generation."
        )

    with open(compliance_path) as f:
        compliance_data = json.load(f)

    status = compliance_data.get("status", "")
    if status == "FAIL":
        issues = compliance_data.get("issues", [])
        raise ComplianceError(
            f"Compliance report has status=FAIL. "
            f"Issues: {issues}. Fix compliance before voiceover generation."
        )

    # --- Check panel_report.json ---
    panel_path = copy_dir / "panel_report.json"
    if not panel_path.exists():
        raise ComplianceError(
            f"panel_report.json not found at {panel_path}. "
            "Run expert panel review before voiceover generation."
        )

    with open(panel_path) as f:
        panel_data = json.load(f)

    average_score = panel_data.get("average_score", 0)
    if average_score < 90:
        raise ComplianceError(
            f"Panel report average_score={average_score} is below 90 threshold. "
            "Revise script and re-run panel review."
        )

    logger.info(
        "Compliance gate passed: status=%s, panel_score=%.1f",
        status,
        average_score,
    )
    return True
