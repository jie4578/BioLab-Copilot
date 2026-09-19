"""Offline tests for the local UI orchestration and file-scope boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biolab_copilot.ui import UIServiceError, UISessionService
from biolab_copilot.ui.app import build_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace() -> Iterator[Path]:
    with TemporaryDirectory(prefix="ui-service-", dir=PROJECT_ROOT / "tests") as value:
        yield Path(value)


def _source(path: Path) -> None:
    path.write_text(
        "sample_id,group,measurement,replicate_type\n"
        "S1,A,1,biological\n"
        "S2,A,2,biological\n"
        "S3,B,4,biological\n"
        "S4,B,5,biological\n",
        encoding="utf-8",
    )


def _mapping() -> dict[str, str]:
    return {
        "sample_id": "sample_id",
        "group": "group",
        "measurement": "measurement",
        "replicate_type": "replicate_type",
    }


def test_sessions_are_isolated_and_service_uses_relative_public_paths(workspace: Path) -> None:
    project = workspace / "project"
    service = UISessionService(project)
    sid_a = service.create_session()
    sid_b = service.create_session()
    assert sid_a != sid_b
    assert service._sessions[sid_a].root != service._sessions[sid_b].root

    source = workspace / "upload.csv"
    _source(source)
    imported = service.import_data(sid_a, source, "generic_grouped", _mapping())
    assert imported["analysis_ready"] is True
    assert str(project) not in json.dumps(imported, ensure_ascii=False)
    assert imported["source_sha256"]
    assert imported["data_preview_total_records"] == 4
    assert imported["data_preview_truncated"] is False
    assert imported["data_preview"][0]["raw_values"]["sample_id"] == "S1"
    assert "source_locations" in imported["data_preview"][0]


def test_confirmation_is_required_and_stale_hash_is_rejected(workspace: Path) -> None:
    service = UISessionService(workspace / "project")
    session_id = service.create_session()
    source = workspace / "upload.csv"
    _source(source)
    service.import_data(session_id, source, "generic_grouped", _mapping())
    plan = service.generate_plan(session_id, "generic_grouped")

    with pytest.raises(UIServiceError):
        service.execute_plan(session_id, plan["plan_sha256"])

    confirmed = service.confirm_plan(
        session_id,
        plan["plan_sha256"],
        {code: True for code in plan["required_confirmations"]},
        explicit_confirmation=True,
    )
    assert confirmed["confirmed"] is True
    plan_path = service._sessions[session_id].plan_path
    assert plan_path is not None
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(UIServiceError):
        service.execute_plan(session_id, confirmed["plan_sha256"])


def test_successful_generic_workflow_and_download_scope(workspace: Path) -> None:
    service = UISessionService(workspace / "project")
    session_id = service.create_session()
    source = workspace / "upload.csv"
    _source(source)
    service.import_data(session_id, source, "generic_grouped", _mapping())
    plan = service.generate_plan(session_id, "generic_grouped")
    confirmed = service.confirm_plan(
        session_id,
        plan["plan_sha256"],
        {code: True for code in plan["required_confirmations"]},
        explicit_confirmation=True,
    )
    run = service.execute_plan(session_id, confirmed["plan_sha256"])
    assert run["status"] == "computed"
    assert run["analysis_ready"] is True
    result_path = service.download_path(
        session_id, f"{run['run_dir']}/analysis_result.json"
    )
    assert result_path.is_file()
    with pytest.raises(UIServiceError):
        service.download_path(session_id, "../outside.json")
    with pytest.raises(UIServiceError):
        service.download_path(session_id, str(result_path))


def test_blocking_import_does_not_execute_and_app_build_is_local_only(workspace: Path) -> None:
    service = UISessionService(workspace / "project")
    session_id = service.create_session()
    source = workspace / "bad.csv"
    source.write_text("sample_id,group\nS1,A\n", encoding="utf-8")
    imported = service.import_data(
        session_id,
        source,
        "generic_grouped",
        {"sample_id": "sample_id", "group": "group"},
    )
    assert imported["analysis_ready"] is False
    plan = service.generate_plan(session_id, "generic_grouped")
    confirmed = service.confirm_plan(
        session_id,
        plan["plan_sha256"],
        {code: True for code in plan["required_confirmations"]},
        explicit_confirmation=True,
    )
    with pytest.raises(UIServiceError):
        service.execute_plan(session_id, confirmed["plan_sha256"])

    app = build_app(service)
    assert app is not None


def test_reimport_invalidates_previous_plan_state(workspace: Path) -> None:
    service = UISessionService(workspace / "project")
    session_id = service.create_session()
    source = workspace / "upload.csv"
    _source(source)
    service.import_data(session_id, source, "generic_grouped", _mapping())
    plan = service.generate_plan(session_id, "generic_grouped")
    service.confirm_plan(
        session_id,
        plan["plan_sha256"],
        {code: True for code in plan["required_confirmations"]},
        explicit_confirmation=True,
    )
    previous_artifact = service._sessions[session_id].import_artifact

    partial = service.import_data(
        session_id,
        source,
        "generic_grouped",
        {"sample_id": "sample_id", "missing_source_column": "measurement"},
    )

    assert partial["analysis_ready"] is False
    session = service._sessions[session_id]
    assert session.import_artifact is not None
    assert session.import_artifact != previous_artifact
    assert session.plan_path is None
    assert session.confirmed_plan_sha256 is None
    assert session.last_run is None
    assert session.last_curve_run is None
