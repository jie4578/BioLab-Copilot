"""Session-scoped orchestration for the local Gradio pilot.

This module deliberately contains no scientific calculations. It calls the existing
ingestion, QC, statistics, and report backends, persists their traceable artifacts, and
returns display-safe summaries to the UI.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biolab_copilot.cli import (
    _run_directory,
    _write_json,
    _write_phase2a_outputs,
    _write_phase2b_outputs,
    _write_phase3a_outputs,
    _write_phase3b_outputs,
    _write_success_outputs,
)
from biolab_copilot.contracts import (
    AnalysisPlan,
    ImportResult,
    IssueSeverity,
    ValidationIssue,
)
from biolab_copilot.ingestion import (
    InputReadError,
    ReaderLimits,
    list_xlsx_sheets,
    read_source,
    sha256_file,
)
from biolab_copilot.paths import project_root as resolve_project_root
from biolab_copilot.profiling import profile_and_validate
from biolab_copilot.reporting import (
    ReportRenderError,
    render_elisa_report,
    render_generic_report,
    render_welch_report,
)
from biolab_copilot.statistics import (
    build_4pl_plan,
    build_analysis_plan,
    build_inverse_plan,
    build_welch_plan,
    compute_4pl_fit,
    compute_grouped_descriptive,
    compute_inverse_result,
    compute_welch_result,
    validate_4pl_execution_inputs,
    validate_execution_inputs,
    validate_inverse_execution_inputs,
    validate_welch_execution_inputs,
)


def _strict_json(path: Path, payload: Any) -> None:
    _write_json(path, payload)


def _issue(
    code: str,
    message: str,
    suggested_action: str,
    *,
    location: str = "ui",
    severity: IssueSeverity = IssueSeverity.BLOCKING,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        location=location,
        suggested_action=suggested_action,
    )


@dataclass
class _Session:
    session_id: str
    root: Path
    import_artifact: Path | None = None
    experiment_type: str | None = None
    plan_path: Path | None = None
    plan_kind: str | None = None
    confirmed_plan_sha256: str | None = None
    last_run: Path | None = None
    last_curve_run: Path | None = None
    runs: dict[str, Path] = field(default_factory=dict)


class UIServiceError(RuntimeError):
    """A user-actionable UI workflow error with structured diagnostics."""

    def __init__(self, message: str, *, issues: list[ValidationIssue] | None = None) -> None:
        self.message = message
        self.issues = issues or [
            _issue(
                "UI_WORKFLOW_ERROR",
                message,
                "Review the displayed workflow state and correct the explicit input.",
            )
        ]
        super().__init__(message)


class UISessionService:
    """Own isolated UI sessions under one project-local output root."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or resolve_project_root()).resolve()
        self.sessions_root = self.project_root / "outputs" / "ui-sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, _Session] = {}

    def create_session(self) -> str:
        """Create a fresh session directory; sessions are never reused."""

        for _ in range(10):
            session_id = f"session-{uuid.uuid4().hex}"
            root = self.sessions_root / session_id
            try:
                root.mkdir(parents=True)
            except FileExistsError:
                continue
            for name in ("input", "imports", "plans", "analyses", "reports"):
                (root / name).mkdir()
            self._sessions[session_id] = _Session(session_id=session_id, root=root)
            _strict_json(
                root / "session.json",
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "created_at": datetime.now(UTC).isoformat(),
                    "scope": "local_ui_session",
                },
            )
            return session_id
        raise UIServiceError("无法创建新的隔离会话目录。")

    def _get(self, session_id: str) -> _Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise UIServiceError(
                "会话不存在或已失效。",
                issues=[
                    _issue(
                        "UI_SESSION_NOT_FOUND",
                        "The UI session does not exist in this process.",
                        "Start a new local UI session and repeat the workflow.",
                    )
                ],
            )
        return session

    @staticmethod
    def _safe_name(value: str) -> str:
        name = Path(value).name
        if not name or name in {".", ".."}:
            raise UIServiceError("上传文件名无效。")
        return name

    @staticmethod
    def _inside(path: Path, root: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise UIServiceError("请求的文件不在当前会话目录内。") from exc
        return resolved

    @staticmethod
    def _sanitize_text(text: str, session: _Session) -> str:
        value = str(text)
        root = str(session.root)
        return value.replace(root, "<session>").replace(root.replace("\\", "/"), "<session>")

    def _public_issue(self, issue: ValidationIssue, session: _Session) -> dict[str, Any]:
        payload = issue.model_dump(mode="json")
        for key, value in list(payload.items()):
            if isinstance(value, str):
                payload[key] = self._sanitize_text(value, session)
        return payload

    def _public_issues(
        self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...], session: _Session
    ) -> list[dict[str, Any]]:
        return [self._public_issue(issue, session) for issue in issues]

    def _public_path(self, path: Path, session: _Session) -> str:
        relative = self._inside(path, session.root).relative_to(session.root)
        return relative.as_posix()

    def _copy_upload(self, uploaded_path: Path, session: _Session) -> Path:
        source = Path(uploaded_path)
        if not source.is_file():
            raise UIServiceError("上传文件不存在，无法导入。")
        suffix = source.suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise UIServiceError("仅支持 CSV 和 XLSX 文件；其他格式会被拒绝。")
        destination = session.root / "input" / self._safe_name(source.name)
        if destination.exists():
            destination = (
                session.root / "input" / (f"{destination.stem}-{uuid.uuid4().hex[:8]}{suffix}")
            )
        shutil.copyfile(source, destination)
        return destination

    @staticmethod
    def _invalidate_analysis_state(session: _Session) -> None:
        """Invalidate current workflow state after a new import attempt.

        Previous successful artifacts remain on disk for auditability, but they
        must not remain eligible for the current UI workflow after a different
        file or mapping is submitted, including a failed import.
        """

        session.import_artifact = None
        session.experiment_type = None
        session.plan_path = None
        session.plan_kind = None
        session.confirmed_plan_sha256 = None
        session.last_run = None
        session.last_curve_run = None

    def list_sheets(
        self, uploaded_path: Path, limits: ReaderLimits | None = None
    ) -> dict[str, Any]:
        """List XLSX sheets without selecting or importing one automatically."""

        path = Path(uploaded_path)
        if path.suffix.lower() != ".xlsx":
            raise UIServiceError("只有 XLSX 文件支持工作表列表。")
        sheets = list_xlsx_sheets(path, limits=limits or ReaderLimits())
        return {"filename": self._safe_name(path.name), "sheets": sheets}

    def import_data(
        self,
        session_id: str,
        uploaded_path: Path,
        experiment_type: str,
        mapping: dict[str, str],
        *,
        sheet_name: str | None = None,
        encoding: str = "utf-8",
        delimiter: str = ",",
        limits: ReaderLimits | None = None,
    ) -> dict[str, Any]:
        """Copy one user upload into the session and run read-only import/QC."""

        session = self._get(session_id)
        if experiment_type not in {"generic_grouped", "elisa_standard_curve"}:
            raise UIServiceError("必须显式选择受支持的实验类型。")
        if not mapping:
            raise UIServiceError("必须提交 source_column 到 canonical_field 的显式列映射。")
        self._invalidate_analysis_state(session)
        source = self._copy_upload(Path(uploaded_path), session)
        reader_limits = limits or ReaderLimits()
        configuration = {
            "experiment_type": experiment_type,
            "sheet": sheet_name,
            "encoding": encoding,
            "delimiter": delimiter,
            "limits": {
                "max_file_bytes": reader_limits.max_file_bytes,
                "max_rows": reader_limits.max_rows,
                "max_uncompressed_bytes": reader_limits.max_uncompressed_bytes,
                "max_zip_members": reader_limits.max_zip_members,
            },
            "source_name": source.name,
        }
        run_id, run_dir = _run_directory(session.root / "imports")
        try:
            table = read_source(
                source,
                sheet_name=sheet_name,
                encoding=encoding,
                delimiter=delimiter,
                limits=reader_limits,
            )
            result = profile_and_validate(
                table,
                experiment_type,
                mapping,
                parse_configuration=configuration,
            )
        except InputReadError as exc:
            issues = list(exc.issues)
            _strict_json(
                run_dir / "validation_issues.json",
                [i.model_dump(mode="json") for i in issues],
            )
            _strict_json(run_dir / "imported_data.json", {"schema_version": "1.0", "records": []})
            return {
                "status": "failed",
                "analysis_ready": False,
                "source_sha256": sha256_file(source),
                "issues": self._public_issues(issues, session),
                "run_dir": self._public_path(run_dir, session),
            }

        result = self._sanitize_import_result(result, source.name)
        started = datetime.now(UTC)
        _write_success_outputs(
            result,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started,
            finished_at=datetime.now(UTC),
            configuration=configuration,
        )
        session.import_artifact = run_dir / "imported_data.json"
        session.experiment_type = experiment_type
        session.plan_path = None
        session.plan_kind = None
        session.confirmed_plan_sha256 = None
        session.last_run = None
        session.last_curve_run = None
        return {
            "status": "completed" if result.analysis_ready else "partial",
            "analysis_ready": result.analysis_ready,
            "source_sha256": result.input_file.sha256,
            "profile": result.dataset_profile.model_dump(mode="json"),
            "issues": self._public_issues(result.validation_issues, session),
            "data_preview": [record.model_dump(mode="json") for record in result.records[:50]],
            "data_preview_total_records": len(result.records),
            "data_preview_truncated": len(result.records) > 50,
            "run_dir": self._public_path(run_dir, session),
            "import_artifact": self._public_path(session.import_artifact, session),
        }

    def _sanitize_import_result(self, result: ImportResult, source_name: str) -> ImportResult:
        """Keep provenance while removing machine-specific absolute paths from UI artifacts."""

        old_path = str(Path(result.input_file.path))

        def clean(value: str) -> str:
            return value.replace(old_path, source_name).replace(
                old_path.replace("\\", "/"), source_name
            )

        input_file = result.input_file.model_copy(update={"path": f"input/{source_name}"})
        records = [
            record.model_copy(
                update={
                    "source_file": source_name,
                    "source_locations": {
                        key: clean(value) for key, value in record.source_locations.items()
                    },
                }
            )
            for record in result.records
        ]
        issues = [
            issue.model_copy(
                update={
                    "source_file": source_name if issue.source_file else None,
                    "location": clean(issue.location),
                }
            )
            for issue in result.validation_issues
        ]
        return result.model_copy(
            update={"input_file": input_file, "records": records, "validation_issues": issues}
        )

    def _load_import(self, session: _Session) -> ImportResult:
        if session.import_artifact is None or not session.import_artifact.is_file():
            raise UIServiceError("请先完成数据导入和结构质控。")
        try:
            return ImportResult.model_validate_json(
                session.import_artifact.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise UIServiceError("当前导入产物无法重新验证，请重新导入数据。") from exc

    def _write_design(self, session: _Session, design: dict[str, Any] | None) -> Path:
        if not isinstance(design, dict) or not design:
            raise UIServiceError("分析设计必须是非空 JSON 对象。")
        path = session.root / "plans" / f"design-{uuid.uuid4().hex}.json"
        _strict_json(path, design)
        return path

    def generate_plan(
        self,
        session_id: str,
        workflow: str,
        *,
        design: dict[str, Any] | None = None,
        curve_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate an unconfirmed plan and any required deterministic preview."""

        session = self._get(session_id)
        imported = self._load_import(session)
        input_artifact = session.import_artifact
        if input_artifact is None:
            raise UIServiceError("请先完成数据导入和结构质控。")
        if workflow not in {"generic_grouped", "welch_two_group", "elisa_4pl", "elisa_inverse"}:
            raise UIServiceError("不支持的分析流程。")
        plan: AnalysisPlan
        preview: Any = None
        issues: list[ValidationIssue] = []
        if workflow == "generic_grouped":
            if imported.experiment_type != "generic_grouped":
                raise UIServiceError("分组描述统计只支持 generic_grouped 导入。")
            plan = build_analysis_plan(input_artifact, imported)
        else:
            if imported.experiment_type != "elisa_standard_curve" and workflow in {
                "elisa_4pl",
                "elisa_inverse",
            }:
                raise UIServiceError("ELISA 流程只支持 elisa_standard_curve 导入。")
            design_path = self._write_design(session, design)
            plan_dir = session.root / "plans" / f"plan-{uuid.uuid4().hex}"
            plan_dir.mkdir()
            if workflow == "welch_two_group":
                if imported.experiment_type != "generic_grouped":
                    raise UIServiceError("Welch 流程只支持 generic_grouped 导入。")
                preview_path = plan_dir / "experimental_units.json"
                welch_build = build_welch_plan(input_artifact, design_path, preview_path)
                preview = welch_build.preview
                issues = list(welch_build.issues)
                _strict_json(preview_path, preview.model_dump(mode="json"))
                plan = welch_build.plan.model_copy(
                    update={"preview_sha256": sha256_file(preview_path)}
                )
            elif workflow == "elisa_4pl":
                preview_path = plan_dir / "standards_preview.json"
                curve_build = build_4pl_plan(input_artifact, design_path, preview_path)
                preview = curve_build.preview
                issues = list(curve_build.issues)
                _strict_json(preview_path, preview.model_dump(mode="json"))
                plan = curve_build.plan.model_copy(
                    update={"standards_preview_sha256": sha256_file(preview_path)}
                )
            else:
                if curve_run_id is None:
                    raise UIServiceError("反算流程必须显式选择当前会话中的 4PL 曲线运行。")
                curve_dir = session.runs.get(curve_run_id)
                if curve_dir is None:
                    raise UIServiceError("指定的曲线运行不存在于当前会话。")
                preview_path = plan_dir / "sample_preview.json"
                inverse_build = build_inverse_plan(
                    curve_dir / "curve_fit_result.json",
                    design_path,
                    preview_path,
                    allowed_root=session.root,
                )
                preview = inverse_build.preview
                issues = list(inverse_build.issues)
                _strict_json(preview_path, preview.model_dump(mode="json"))
                plan = inverse_build.plan.model_copy(
                    update={"inverse_preview_sha256": sha256_file(preview_path)}
                )
            plan_path = plan_dir / "analysis_plan.json"
        if workflow == "generic_grouped":
            plan_dir = session.root / "plans" / f"plan-{uuid.uuid4().hex}"
            plan_dir.mkdir()
            plan_path = plan_dir / "analysis_plan.json"
        _strict_json(plan_path, plan.model_dump(mode="json"))
        plan_sha = sha256_file(plan_path)
        session.plan_path = plan_path
        session.plan_kind = workflow
        session.confirmed_plan_sha256 = None
        return {
            "workflow": workflow,
            "plan_id": plan.plan_id,
            "plan_sha256": plan_sha,
            "confirmed": False,
            "required_confirmations": plan.required_confirmations,
            "plan": self._public_plan(plan, session),
            "preview": preview.model_dump(mode="json") if preview is not None else None,
            "issues": self._public_issues(issues, session),
            "plan_path": self._public_path(plan_path, session),
        }

    def _public_plan(self, plan: AnalysisPlan, session: _Session) -> dict[str, Any]:
        payload = plan.model_dump(mode="json")
        path_keys = {
            "input_artifact_path",
            "design_declaration_path",
            "experimental_unit_preview_path",
            "standards_preview_path",
            "curve_design_path",
            "inverse_curve_fit_result_path",
            "inverse_curve_plan_path",
            "inverse_curve_preview_path",
            "inverse_curve_manifest_path",
            "inverse_design_path",
            "inverse_sample_artifact_path",
            "inverse_preview_path",
        }
        for key in path_keys:
            value = payload.get(key)
            if isinstance(value, str):
                try:
                    payload[key] = self._public_path(Path(value), session)
                except UIServiceError:
                    payload[key] = "<session-scoped path>"
        return payload

    def confirm_plan(
        self,
        session_id: str,
        expected_plan_sha256: str,
        warning_confirmations: dict[str, bool],
        *,
        explicit_confirmation: bool,
    ) -> dict[str, Any]:
        """Require a deliberate UI action, then persist and re-hash the confirmed plan."""

        session = self._get(session_id)
        if not explicit_confirmation:
            raise UIServiceError("必须勾选明确的计划确认项后才能确认。")
        if session.plan_path is None or session.plan_kind is None:
            raise UIServiceError("请先生成分析计划。")
        current_sha = sha256_file(session.plan_path)
        if current_sha.lower() != expected_plan_sha256.lower():
            raise UIServiceError(
                "计划文件已变化，旧 SHA-256 确认已失效。",
                issues=[
                    _issue(
                        "PLAN_HASH_MISMATCH",
                        "The displayed plan SHA-256 does not match the current plan.",
                        "Regenerate the displayed hash and review the current plan again.",
                    )
                ],
            )
        try:
            plan = AnalysisPlan.model_validate_json(session.plan_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UIServiceError("当前计划无法验证。") from exc
        confirmations = {
            code: bool(warning_confirmations.get(code, False))
            for code in plan.required_confirmations
        }
        missing = [code for code, value in confirmations.items() if not value]
        if missing:
            raise UIServiceError(
                "仍有需要人工确认的警告未勾选。",
                issues=[
                    _issue(
                        "WARNING_CONFIRMATION_MISSING",
                        f"Warning confirmations are missing: {', '.join(missing)}.",
                        "Review and explicitly confirm each listed warning before execution.",
                    )
                ],
            )
        confirmed = plan.model_copy(
            update={"confirmed": True, "warning_confirmations": confirmations}
        )
        _strict_json(session.plan_path, confirmed.model_dump(mode="json"))
        confirmed_sha = sha256_file(session.plan_path)
        session.confirmed_plan_sha256 = confirmed_sha
        return {
            "confirmed": True,
            "plan_sha256": confirmed_sha,
            "plan": self._public_plan(confirmed, session),
            "message": "计划已确认；执行时仍会重新验证输入、配置和该 SHA-256。",
        }

    def _require_confirmed(self, session: _Session, confirmed_plan_sha256: str) -> Path:
        if session.plan_path is None or session.plan_kind is None:
            raise UIServiceError("请先生成并确认分析计划。")
        if session.confirmed_plan_sha256 is None:
            raise UIServiceError("当前会话没有已确认的计划。")
        if confirmed_plan_sha256.lower() != session.confirmed_plan_sha256.lower():
            raise UIServiceError("提交的计划 SHA-256 不是当前会话的已确认值。")
        return session.plan_path

    @staticmethod
    def _blocking(
        issues: list[ValidationIssue] | tuple[ValidationIssue, ...],
    ) -> list[ValidationIssue]:
        return [
            issue
            for issue in issues
            if issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
        ]

    def execute_plan(self, session_id: str, confirmed_plan_sha256: str) -> dict[str, Any]:
        """Revalidate all bindings and execute one existing deterministic backend plan."""

        session = self._get(session_id)
        plan_path = self._require_confirmed(session, confirmed_plan_sha256)
        started = datetime.now(UTC)
        kind = session.plan_kind
        result: Any
        if kind == "generic_grouped":
            generic_preflight = validate_execution_inputs(
                plan_path, confirmed_plan_sha256, allowed_root=session.root
            )
            imported = generic_preflight.import_result
            issues = [*(imported.validation_issues if imported else ()), *generic_preflight.issues]
            blocked = self._blocking(issues)
            if blocked or imported is None:
                raise UIServiceError(
                    "QC 或计划校验未通过，禁止执行描述统计。", issues=blocked or issues
                )
            result = compute_grouped_descriptive(
                imported, generic_preflight.plan, generic_preflight.plan_sha256
            )
            run_id, run_dir = _run_directory(session.root / "analyses" / "generic_grouped")
            _write_phase2a_outputs(
                plan_bytes=plan_path.read_bytes(),
                plan=generic_preflight.plan,
                result=result,
                issues=result.issues,
                plan_sha256=generic_preflight.plan_sha256,
                run_id=run_id,
                run_dir=run_dir,
                started_at=started,
                finished_at=datetime.now(UTC),
                configuration={"workflow": kind, "ui_session": session.session_id},
                import_result=imported,
            )
        elif kind == "welch_two_group":
            welch_preflight = validate_welch_execution_inputs(
                plan_path, confirmed_plan_sha256, allowed_root=session.root
            )
            imported = welch_preflight.import_result
            issues = [*(imported.validation_issues if imported else ()), *welch_preflight.issues]
            blocked = self._blocking(issues)
            if blocked or imported is None:
                raise UIServiceError(
                    "QC 或实验设计校验未通过，禁止执行 Welch 分析。", issues=blocked or issues
                )
            result = compute_welch_result(welch_preflight)
            run_id, run_dir = _run_directory(session.root / "analyses" / "welch_two_group")
            _write_phase2b_outputs(
                plan_bytes=plan_path.read_bytes(),
                plan=welch_preflight.plan,
                preview=welch_preflight.preview,
                result=result,
                issues=result.issues,
                plan_sha256=welch_preflight.plan_sha256,
                run_id=run_id,
                run_dir=run_dir,
                started_at=started,
                finished_at=datetime.now(UTC),
                configuration={"workflow": kind, "ui_session": session.session_id},
                import_result=imported,
            )
        elif kind == "elisa_4pl":
            curve_preflight = validate_4pl_execution_inputs(
                plan_path, confirmed_plan_sha256, allowed_root=session.root
            )
            imported = curve_preflight.import_result
            issues = [*(imported.validation_issues if imported else ()), *curve_preflight.issues]
            blocked = self._blocking(issues)
            if blocked or imported is None:
                raise UIServiceError(
                    "QC 或 4PL 计划校验未通过，禁止拟合。", issues=blocked or issues
                )
            result = compute_4pl_fit(curve_preflight)
            run_id, run_dir = _run_directory(session.root / "analyses" / "elisa_4pl")
            _write_phase3a_outputs(
                plan_bytes=plan_path.read_bytes(),
                plan=curve_preflight.plan,
                preview=curve_preflight.preview,
                result=result,
                issues=result.issues,
                plan_sha256=curve_preflight.plan_sha256,
                run_id=run_id,
                run_dir=run_dir,
                started_at=started,
                finished_at=datetime.now(UTC),
                configuration={"workflow": kind, "ui_session": session.session_id},
                import_result=imported,
            )
        elif kind == "elisa_inverse":
            inverse_preflight = validate_inverse_execution_inputs(
                plan_path, confirmed_plan_sha256, allowed_root=session.root
            )
            imported = inverse_preflight.sample_import
            issues = [*(imported.validation_issues if imported else ()), *inverse_preflight.issues]
            blocked = self._blocking(issues)
            if blocked or imported is None:
                raise UIServiceError(
                    "曲线、样本或计划校验未通过，禁止反算。", issues=blocked or issues
                )
            result = compute_inverse_result(inverse_preflight)
            run_id, run_dir = _run_directory(session.root / "analyses" / "elisa_inverse")
            _write_phase3b_outputs(
                plan_bytes=plan_path.read_bytes(),
                plan=inverse_preflight.plan,
                result=result,
                issues=result.issues,
                plan_sha256=inverse_preflight.plan_sha256,
                run_id=run_id,
                run_dir=run_dir,
                started_at=started,
                finished_at=datetime.now(UTC),
                configuration={"workflow": kind, "ui_session": session.session_id},
                preflight=inverse_preflight,
            )
        else:  # pragma: no cover - guarded by generate_plan
            raise UIServiceError("未知的计划流程。")
        session.runs[run_id] = run_dir
        session.last_run = run_dir
        if kind == "elisa_4pl":
            session.last_curve_run = run_dir
        return {
            "run_id": run_id,
            "status": result.status,
            "analysis_ready": result.status == "computed",
            "plan_sha256": confirmed_plan_sha256,
            "run_dir": self._public_path(run_dir, session),
            "issues": self._public_issues(result.issues, session),
            "result": result.model_dump(mode="json"),
        }

    def render_report(
        self,
        session_id: str,
        report_type: str,
        run_id: str,
        *,
        inverse_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Render an existing completed run into a new session-scoped package."""

        session = self._get(session_id)
        run_dir = session.runs.get(run_id)
        if run_dir is None:
            raise UIServiceError("报告来源运行不属于当前会话。")
        (session.root / "reports").mkdir(parents=True, exist_ok=True)
        output_dir = session.root / "reports" / f"report-{uuid.uuid4().hex}"
        try:
            if report_type == "generic_grouped":
                manifest = render_generic_report(run_dir, output_dir)
            elif report_type == "welch_two_group":
                manifest = render_welch_report(run_dir, output_dir)
            elif report_type == "elisa_4pl":
                inverse_dir = session.runs.get(inverse_run_id) if inverse_run_id else None
                manifest = render_elisa_report(run_dir, output_dir, inverse_dir)
            else:
                raise UIServiceError("不支持的报告类型。")
        except (ReportRenderError, OSError, ValueError) as exc:
            raise UIServiceError(f"报告生成失败：{type(exc).__name__}。") from exc
        files = sorted(
            self._public_path(path, session) for path in output_dir.rglob("*") if path.is_file()
        )
        return {
            "report_manifest": self._public_path(manifest, session),
            "files": files,
            "report_dir": self._public_path(output_dir, session),
        }

    def download_path(self, session_id: str, relative_path: str) -> Path:
        """Resolve only an existing file inside the current session."""

        session = self._get(session_id)
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise UIServiceError("下载路径被拒绝：必须是当前会话内的相对路径。")
        resolved = self._inside(session.root / candidate, session.root)
        if not resolved.is_file():
            raise UIServiceError("下载文件不存在或不是本次会话生成的文件。")
        return resolved

    def session_summary(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        return {
            "session_id": session.session_id,
            "scope": "local_ui_session",
            "import_artifact": (
                self._public_path(session.import_artifact, session)
                if session.import_artifact
                else None
            ),
            "plan": self._public_path(session.plan_path, session) if session.plan_path else None,
            "confirmed_plan_sha256": session.confirmed_plan_sha256,
            "runs": sorted(session.runs),
        }


__all__ = ["UIServiceError", "UISessionService"]
