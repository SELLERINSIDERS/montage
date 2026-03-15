"""Tests for compliance gate logic.

Validates that check_compliance() blocks voiceover generation when:
- compliance_report.json is missing
- compliance_report.json has FAIL status
- panel_report.json is missing
- panel_report.json average_score < 90
- both reports pass (returns True)
"""

import json

import pytest

from video.kling.compliance_gate import ComplianceError, check_compliance


class TestComplianceGate:
    """check_compliance validates compliance and panel reports before voiceover."""

    def test_raises_when_compliance_report_missing(self, tmp_path):
        """Missing compliance_report.json raises ComplianceError."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        # panel_report exists but compliance_report does not
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 95})
        )

        with pytest.raises(ComplianceError, match="compliance_report.json"):
            check_compliance(tmp_path)

    def test_raises_when_compliance_report_fails(self, tmp_path):
        """compliance_report.json with status=FAIL raises ComplianceError."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "FAIL", "issues": ["disease claim found"]})
        )
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 95})
        )

        with pytest.raises(ComplianceError, match="FAIL"):
            check_compliance(tmp_path)

    def test_raises_when_panel_report_missing(self, tmp_path):
        """Missing panel_report.json raises ComplianceError."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "PASS"})
        )

        with pytest.raises(ComplianceError, match="panel_report.json"):
            check_compliance(tmp_path)

    def test_raises_when_panel_score_below_90(self, tmp_path):
        """panel_report.json with average_score < 90 raises ComplianceError."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "PASS"})
        )
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 85.5})
        )

        with pytest.raises(ComplianceError, match="90"):
            check_compliance(tmp_path)

    def test_returns_true_when_both_pass(self, tmp_path):
        """Both reports valid and passing returns True."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "PASS"})
        )
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 92.0})
        )

        assert check_compliance(tmp_path) is True

    def test_pass_with_warnings_allowed(self, tmp_path):
        """status='PASS WITH WARNINGS' should not raise."""
        copy_dir = tmp_path / "copy"
        copy_dir.mkdir()
        (copy_dir / "compliance_report.json").write_text(
            json.dumps({"status": "PASS WITH WARNINGS"})
        )
        (copy_dir / "panel_report.json").write_text(
            json.dumps({"average_score": 91})
        )

        assert check_compliance(tmp_path) is True
