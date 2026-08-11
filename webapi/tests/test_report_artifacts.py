from pathlib import Path

import app.reports.artifacts as artifacts


def test_save_and_resolve_report_artifact(tmp_path: Path, monkeypatch) -> None:
    report_dir = tmp_path / "data" / "reports"
    monkeypatch.setattr(artifacts, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "REPORT_DIR", report_dir)

    relative_path, size = artifacts.save_report_artifact(b"%PDF-test", 42, "pdf")

    assert relative_path == "data/reports/report-history-42.pdf"
    assert size == 9
    assert artifacts.resolve_report_artifact(relative_path) == (
        report_dir / "report-history-42.pdf"
    )


def test_resolve_report_artifact_rejects_paths_outside_report_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "data" / "reports"
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"secret")
    monkeypatch.setattr(artifacts, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "REPORT_DIR", report_dir)

    assert artifacts.resolve_report_artifact("secret.pdf") is None
