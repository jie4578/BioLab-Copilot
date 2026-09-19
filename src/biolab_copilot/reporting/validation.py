"""Read-only validation of completed analysis packages for Phase 4A reports."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from biolab_copilot.contracts import (
    AnalysisPlan,
    AnalysisResult,
    CurveFitResult,
    ExperimentalUnitsPreview,
    ImportResult,
    IssueSeverity,
    RunManifest,
    SampleConcentrationsResult,
    StandardsPreview,
)
from biolab_copilot.paths import project_root

SCHEMA_VERSION = "1.0"
MODEL = TypeVar("MODEL", bound=BaseModel)


class UpstreamValidationError(ValueError):
    """Raised when a report source package is incomplete or has changed."""

    def __init__(self, message: str, *, code: str = "UPSTREAM_INVALID") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnalysisPackage:
    root: Path
    manifest_path: Path
    manifest: RunManifest
    manifest_sha256: str
    plan_path: Path
    plan: AnalysisPlan
    plan_sha256: str
    result_path: Path
    result: BaseModel
    artifacts: dict[str, Path]
    artifact_hashes: dict[str, str]
    input_artifact_path: Path
    input_artifact: ImportResult
    issues: list[dict[str, Any]]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_finite(value: Any, *, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise UpstreamValidationError(f"Non-finite JSON number at {path}.", code="NONFINITE_JSON")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite(item, path=f"{path}[{index}]")


def load_json(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpstreamValidationError(
            f"Unable to read JSON artifact {path.name}: {type(exc).__name__}.",
            code="JSON_INVALID",
        ) from exc
    _assert_finite(payload)
    return payload


def _model(path: Path, model_type: type[MODEL]) -> MODEL:
    try:
        return model_type.model_validate(load_json(path))
    except UpstreamValidationError:
        raise
    except ValueError as exc:
        raise UpstreamValidationError(
            f"Artifact {path.name} does not satisfy the supported schema.",
            code="SCHEMA_UNSUPPORTED",
        ) from exc


def _inside(path: Path, root: Path, *, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise UpstreamValidationError(
            f"{label} is outside the project directory.", code="PATH_OUTSIDE_PROJECT"
        ) from exc
    return resolved


def _inside_run(path: Path, run_dir: Path, *, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise UpstreamValidationError(
            f"{label} is not inside the declared analysis directory.",
            code="PATH_OUTSIDE_ANALYSIS_DIR",
        ) from exc
    return resolved


def _artifact_index(manifest: RunManifest, run_dir: Path) -> tuple[dict[str, Path], dict[str, str]]:
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for artifact in manifest.output_files:
        path = _inside_run(Path(artifact.path), run_dir, label=artifact.artifact_type)
        if not path.is_file():
            raise UpstreamValidationError(
                f"Manifest artifact {artifact.artifact_type} is missing.",
                code="ARTIFACT_MISSING",
            )
        actual = sha256_file(path)
        if actual != artifact.sha256:
            raise UpstreamValidationError(
                f"Hash mismatch for {artifact.artifact_type}.", code="HASH_MISMATCH"
            )
        paths[artifact.artifact_type] = path
        hashes[artifact.artifact_type] = actual
    return paths, hashes


def _required_artifact(paths: dict[str, Path], run_dir: Path, name: str) -> Path:
    path = paths.get(name)
    if path is None:
        path = run_dir / f"{name}.json"
    if not path.is_file():
        raise UpstreamValidationError(
            f"Required artifact {name} is missing.", code="ARTIFACT_MISSING"
        )
    return path


def _issues(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = load_json(path)
    if not isinstance(payload, list):
        raise UpstreamValidationError(
            "analysis_issues.json must contain a list.", code="SCHEMA_UNSUPPORTED"
        )
    return [dict(item) for item in payload]


def _validate_manifest_status(manifest: RunManifest) -> None:
    if manifest.status not in {"COMPLETED", "PARTIAL"}:
        raise UpstreamValidationError(
            "A failed or incomplete upstream run cannot produce a complete report.",
            code="UPSTREAM_RUN_NOT_REPORTABLE",
        )
    if manifest.schema_version != SCHEMA_VERSION:
        raise UpstreamValidationError(
            "Unsupported manifest schema version.", code="SCHEMA_UNSUPPORTED"
        )


def _validate_plan_binding(
    *,
    plan: AnalysisPlan,
    plan_path: Path,
    manifest: RunManifest,
    result: BaseModel,
    project_root: Path,
) -> tuple[Path, ImportResult]:
    plan_sha = sha256_file(plan_path)
    if manifest.analysis_plan_sha256 != plan_sha:
        raise UpstreamValidationError(
            "Manifest does not bind the current plan.", code="HASH_MISMATCH"
        )
    if not plan.confirmed:
        raise UpstreamValidationError(
            "The upstream plan is not confirmed.", code="PLAN_NOT_CONFIRMED"
        )
    if isinstance(result, AnalysisResult | CurveFitResult | SampleConcentrationsResult):
        confirmed = result.confirmed_plan_sha256
        if confirmed != plan_sha:
            raise UpstreamValidationError(
                "The result does not bind the current confirmed plan.", code="HASH_MISMATCH"
            )
    if not plan.input_artifact_path or not plan.input_artifact_sha256:
        raise UpstreamValidationError(
            "The upstream plan has no input artifact binding.", code="PROVENANCE_MISSING"
        )
    input_path = _inside(Path(plan.input_artifact_path), project_root, label="input artifact")
    if not input_path.is_file() or sha256_file(input_path) != plan.input_artifact_sha256:
        raise UpstreamValidationError(
            "The bound input artifact changed or is missing.", code="HASH_MISMATCH"
        )
    imported = _model(input_path, ImportResult)
    if imported.input_file.sha256 != plan.source_sha256:
        raise UpstreamValidationError(
            "The source hash binding is inconsistent.", code="HASH_MISMATCH"
        )
    return input_path, imported


def load_package(
    analysis_dir: Path,
    *,
    expected_assay: str,
    result_type: type[MODEL],
    expected_level: str,
) -> AnalysisPackage:
    """Load and verify one explicit completed analysis directory."""
    root = project_root()
    run_dir = _inside(analysis_dir, root, label="analysis directory")
    if not run_dir.is_dir():
        raise UpstreamValidationError(
            "Analysis directory does not exist.", code="ANALYSIS_DIR_MISSING"
        )
    manifest_path = run_dir / "run_manifest.json"
    manifest = _model(manifest_path, RunManifest)
    _validate_manifest_status(manifest)
    if manifest.assay_type != expected_assay or manifest.analysis_level != expected_level:
        raise UpstreamValidationError(
            "Analysis type or level does not match the report command.", code="TYPE_MISMATCH"
        )
    paths, hashes = _artifact_index(manifest, run_dir)
    plan_path = _required_artifact(paths, run_dir, "analysis_plan")
    result_name = {
        AnalysisResult: "analysis_result",
        CurveFitResult: "curve_fit_result",
        SampleConcentrationsResult: "sample_concentrations",
    }.get(result_type)
    if result_name is None:
        raise UpstreamValidationError("Unsupported report result type.", code="TYPE_MISMATCH")
    result_path = _required_artifact(paths, run_dir, result_name)
    plan = _model(plan_path, AnalysisPlan)
    result = _model(result_path, result_type)
    if (
        plan.schema_version != SCHEMA_VERSION
        or getattr(result, "schema_version", None) != SCHEMA_VERSION
    ):
        raise UpstreamValidationError(
            "Unsupported upstream schema version.", code="SCHEMA_UNSUPPORTED"
        )
    input_path, imported = _validate_plan_binding(
        plan=plan,
        plan_path=plan_path,
        manifest=manifest,
        result=result,
        project_root=root,
    )
    manifest_sha = sha256_file(manifest_path)
    return AnalysisPackage(
        root=run_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_sha256=manifest_sha,
        plan_path=plan_path,
        plan=plan,
        plan_sha256=sha256_file(plan_path),
        result_path=result_path,
        result=result,
        artifacts=paths,
        artifact_hashes=hashes,
        input_artifact_path=input_path,
        input_artifact=imported,
        issues=_issues(paths.get("analysis_issues")),
    )


def load_generic_package(analysis_dir: Path) -> AnalysisPackage:
    package = load_package(
        analysis_dir,
        expected_assay="generic_grouped",
        result_type=AnalysisResult,
        expected_level="measurement_rows",
    )
    result = package.result
    assert isinstance(result, AnalysisResult)
    if result.status != "computed" or not package.manifest.analysis_ready:
        raise UpstreamValidationError(
            "Generic result is not complete and analysis-ready.", code="UPSTREAM_NOT_READY"
        )
    if result.analysis_level != "measurement_rows":
        raise UpstreamValidationError(
            "Generic result is not measurement-row level.", code="TYPE_MISMATCH"
        )
    return package


def load_welch_package(analysis_dir: Path) -> tuple[AnalysisPackage, ExperimentalUnitsPreview]:
    package = load_package(
        analysis_dir,
        expected_assay="generic_grouped",
        result_type=AnalysisResult,
        expected_level="experimental_units",
    )
    result = package.result
    assert isinstance(result, AnalysisResult)
    if result.status != "computed" or not package.manifest.analysis_ready:
        raise UpstreamValidationError(
            "Welch result is not complete and analysis-ready.", code="UPSTREAM_NOT_READY"
        )
    if result.method != "welch_t" or result.alternative != "two-sided":
        raise UpstreamValidationError(
            "The upstream result is not the supported Welch comparison.", code="TYPE_MISMATCH"
        )
    preview_path = _required_artifact(package.artifacts, package.root, "experimental_units")
    preview = _model(preview_path, ExperimentalUnitsPreview)
    if package.manifest.preview_sha256 != sha256_file(preview_path):
        raise UpstreamValidationError(
            "Experimental-unit preview hash mismatch.", code="HASH_MISMATCH"
        )
    if result.preview_sha256 != package.manifest.preview_sha256:
        raise UpstreamValidationError(
            "Welch result preview binding is inconsistent.", code="HASH_MISMATCH"
        )
    return package, preview


def load_elisa_curve_package(analysis_dir: Path) -> tuple[AnalysisPackage, StandardsPreview]:
    package = load_package(
        analysis_dir,
        expected_assay="elisa_standard_curve",
        result_type=CurveFitResult,
        expected_level="standard_curve_levels",
    )
    result = package.result
    assert isinstance(result, CurveFitResult)
    if result.status != "computed" or not package.manifest.analysis_ready:
        raise UpstreamValidationError(
            "ELISA curve result is not complete and analysis-ready.", code="UPSTREAM_NOT_READY"
        )
    if result.curve_validated is not False or result.quantification_enabled is not False:
        raise UpstreamValidationError(
            "ELISA validation flags were changed.", code="SEMANTICS_INVALID"
        )
    preview_path = _required_artifact(package.artifacts, package.root, "standards_preview")
    preview = _model(preview_path, StandardsPreview)
    if package.manifest.standards_preview_sha256 != sha256_file(preview_path):
        raise UpstreamValidationError("Standards preview hash mismatch.", code="HASH_MISMATCH")
    if result.standards_preview_sha256 != package.manifest.standards_preview_sha256:
        raise UpstreamValidationError(
            "Curve result preview binding is inconsistent.", code="HASH_MISMATCH"
        )
    if (
        preview.direction != result.direction
        or preview.concentration_unit != result.concentration_unit
    ):
        raise UpstreamValidationError(
            "Curve preview semantics do not match the result.", code="TYPE_MISMATCH"
        )
    return package, preview


def load_elisa_inverse_package(analysis_dir: Path) -> AnalysisPackage:
    package = load_package(
        analysis_dir,
        expected_assay="elisa_standard_curve",
        result_type=SampleConcentrationsResult,
        expected_level="measurement_rows",
    )
    result = package.result
    assert isinstance(result, SampleConcentrationsResult)
    if result.intended_use != "research_only" or not result.research_only_acknowledged:
        raise UpstreamValidationError(
            "Inverse result is not explicitly research-only.", code="SEMANTICS_INVALID"
        )
    if result.curve_validated is not False or result.validated_quantification_enabled is not False:
        raise UpstreamValidationError(
            "Inverse validation flags were changed.", code="SEMANTICS_INVALID"
        )
    return package


def validate_elisa_inverse_binding(
    curve: AnalysisPackage,
    inverse: AnalysisPackage,
) -> None:
    curve_result = curve.result
    inverse_result = inverse.result
    if not isinstance(curve_result, CurveFitResult) or not isinstance(
        inverse_result, SampleConcentrationsResult
    ):
        raise UpstreamValidationError("ELISA package types are inconsistent.", code="TYPE_MISMATCH")
    if inverse_result.curve_fit_result_sha256 != sha256_file(curve.result_path):
        raise UpstreamValidationError(
            "Inverse result is not bound to the selected curve.", code="HASH_MISMATCH"
        )
    if inverse.manifest.curve_fit_result_sha256 != sha256_file(curve.result_path):
        raise UpstreamValidationError(
            "Inverse manifest is not bound to the selected curve.", code="HASH_MISMATCH"
        )
    if inverse_result.direction != curve_result.direction:
        raise UpstreamValidationError(
            "Curve direction differs between ELISA packages.", code="TYPE_MISMATCH"
        )
    if (
        inverse_result.concentration_unit != curve_result.concentration_unit
        or inverse_result.response_unit != curve_result.response_unit
    ):
        raise UpstreamValidationError(
            "ELISA units differ between curve and inverse packages.", code="TYPE_MISMATCH"
        )
    if inverse_result.curve_validated is not False or curve_result.curve_validated is not False:
        raise UpstreamValidationError(
            "ELISA validation semantics are inconsistent.", code="SEMANTICS_INVALID"
        )


def warning_count(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in IssueSeverity}
    for issue in issues:
        severity = str(issue.get("severity", "warning"))
        if severity in counts:
            counts[severity] += 1
    return counts


__all__ = [
    "AnalysisPackage",
    "SCHEMA_VERSION",
    "UpstreamValidationError",
    "load_elisa_curve_package",
    "load_elisa_inverse_package",
    "load_generic_package",
    "load_json",
    "load_welch_package",
    "sha256_file",
    "validate_elisa_inverse_binding",
    "warning_count",
]
