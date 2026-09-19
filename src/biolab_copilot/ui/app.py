"""Small, explicit Gradio surface over :mod:`biolab_copilot.ui.service`."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from biolab_copilot import __version__

from .service import UIServiceError, UISessionService


def _json_object(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise UIServiceError(f"{label} 不是有效 JSON：{exc.msg}。") from exc
    if not isinstance(value, dict):
        raise UIServiceError(f"{label} 必须是 JSON 对象。")
    return value


def _error(exc: UIServiceError) -> tuple[str, dict[str, Any]]:
    return exc.message, {"issues": [issue.model_dump(mode="json") for issue in exc.issues]}


def build_app(service: UISessionService | None = None) -> Any:
    """Build the local app without performing a network request or scientific calculation."""

    try:
        gr = importlib.import_module("gradio")
    except ImportError as exc:  # pragma: no cover - exercised by packaging environments
        raise RuntimeError(
            "未安装 Gradio。请在项目环境中安装可选依赖：python -m pip install -e \".[ui]\"。"
        ) from exc

    workflow_choices = [
        ("Generic grouped 描述统计", "generic_grouped"),
        ("Welch 两组分析", "welch_two_group"),
        ("ELISA 4PL 标准曲线拟合", "elisa_4pl"),
        ("ELISA research-only 浓度反算", "elisa_inverse"),
    ]
    service = service or UISessionService()

    with gr.Blocks(title="BioLab Copilot — Local Pilot") as demo:
        session_state = gr.State("")
        plan_hash_state = gr.State("")
        gr.Markdown(
            "# BioLab Copilot\n"
            "本地优先、结果可追溯的生物实验数据分析试运行界面。"
        )
        with gr.Tab("首页"):
            gr.Markdown(
                f"**版本**：`{__version__}`  \n"
                "**运行方式**：仅本机 `127.0.0.1`，无云端服务、无遥测、无 AI Provider。  \n"
                "**研究用途声明**：结果不是实验验证、诊断、疗效或已验证定量结论。  \n"
                "**支持流程**：generic grouped 描述统计、Welch 两组分析、ELISA 4PL 拟合、"
                "ELISA research-only 逐记录反算，以及确定性 Word/Excel/JSON/PNG 报告。"
            )
            session_text = gr.Textbox(label="本次隔离会话", interactive=False)
            session_status = gr.Markdown()

        with gr.Tab("导入与结构 QC"):
            gr.Markdown(
                "实验类型、工作表和列映射必须显式选择。建议列名只提供给用户参考；"
                "不会自动套用映射。"
            )
            upload = gr.File(label="CSV/XLSX 文件", file_types=[".csv", ".xlsx"], type="filepath")
            assay = gr.Dropdown(
                choices=[
                    ("Generic grouped", "generic_grouped"),
                    ("ELISA standard curve", "elisa_standard_curve"),
                ],
                value=None,
                label="实验类型（必选）",
            )
            with gr.Row():
                sheet = gr.Textbox(label="XLSX 工作表名称（多表时必填）")
                encoding = gr.Textbox(value="utf-8", label="CSV 编码")
                delimiter = gr.Textbox(value=",", label="CSV 分隔符")
            mapping = gr.Textbox(
                label="显式列映射 JSON（source_column -> canonical_field）",
                lines=4,
                placeholder='{"Group":"group","Value":"measurement"}',
            )
            with gr.Row():
                list_sheets_button = gr.Button("查看 XLSX 工作表")
                import_button = gr.Button("导入并执行结构 QC", variant="primary")
            sheet_result = gr.JSON(label="可选工作表")
            import_status = gr.Markdown()
            import_result = gr.JSON(label="DatasetProfile / ValidationIssue")
            import_preview = gr.JSON(label="数据预览：原始值、解析值和来源位置")

        with gr.Tab("计划、确认与执行"):
            workflow = gr.Dropdown(
                choices=workflow_choices,
                value=None,
                label="分析流程（必选）",
            )
            design = gr.Textbox(
                label="分析设计 JSON（Welch/4PL/反算必须显式提供）",
                lines=10,
                placeholder="粘贴现有契约要求的设计声明 JSON；不会自动推断。",
            )
            curve_run_id = gr.Textbox(
                label="反算使用的本会话 4PL run_id（仅 inverse）"
            )
            generate_button = gr.Button("生成未确认计划")
            plan_status = gr.Markdown()
            plan_payload = gr.JSON(label="计划摘要、预览、QC issue")
            plan_hash = gr.Textbox(label="当前计划 SHA-256", interactive=False)
            warning_confirmations = gr.Textbox(
                label="逐项警告确认 JSON（例如 {\"CODE\": true}）",
                value="{}",
                lines=3,
            )
            explicit_confirmation = gr.Checkbox(
                label="我已审阅当前计划、预览和全部列出的警告，并确认该计划 SHA-256",
                value=False,
            )
            confirm_button = gr.Button("确认计划")
            execute_button = gr.Button("执行已确认分析", variant="primary")
            execute_status = gr.Markdown()
            execute_payload = gr.JSON(label="运行结果、issues、结构化统计")

        with gr.Tab("报告与下载"):
            report_type = gr.Dropdown(
                choices=[
                    ("Generic grouped", "generic_grouped"),
                    ("Welch two-group", "welch_two_group"),
                    ("ELISA 4PL", "elisa_4pl"),
                ],
                value=None,
                label="报告类型（必选）",
            )
            report_run_id = gr.Textbox(label="报告来源 run_id")
            inverse_report_run_id = gr.Textbox(label="可选的 inverse run_id（ELISA 报告）")
            report_button = gr.Button("生成 Word/Excel/JSON/PNG 报告")
            report_status = gr.Markdown()
            report_payload = gr.JSON(label="报告文件（仅当前会话相对路径）")
            download_relative = gr.Textbox(label="要下载的会话内相对路径")
            download_button = gr.Button("下载文件")
            download_status = gr.Markdown()
            download_file = gr.File(label="下载")

        def start_session() -> tuple[str, str, str]:
            session_id = service.create_session()
            return session_id, session_id, "状态：**会话已隔离创建**。"

        def list_sheets(uploaded: str | None) -> dict[str, Any]:
            if not uploaded:
                return {"error": "请先选择 XLSX 文件。"}
            try:
                return service.list_sheets(Path(uploaded))
            except UIServiceError as exc:
                return {
                    "error": exc.message,
                    "issues": [i.model_dump(mode="json") for i in exc.issues],
                }

        def import_callback(
            session_id: str,
            uploaded: str | None,
            assay_value: str | None,
            mapping_text: str,
            sheet_name: str,
            encoding_value: str,
            delimiter_value: str,
        ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
            try:
                if not session_id:
                    raise UIServiceError("会话尚未创建，请刷新页面后重试。")
                if not uploaded or not assay_value:
                    raise UIServiceError("文件和实验类型都必须显式选择。")
                result = service.import_data(
                    session_id,
                    Path(uploaded),
                    assay_value,
                    _json_object(mapping_text, "列映射"),
                    sheet_name=sheet_name.strip() or None,
                    encoding=encoding_value.strip() or "utf-8",
                    delimiter=delimiter_value or ",",
                )
                return (
                    "导入完成；请审阅数据预览、DatasetProfile 和全部 QC issue。",
                    result,
                    result.get("data_preview", []),
                )
            except UIServiceError as exc:
                message, payload = _error(exc)
                return f"导入未完成：{message}", payload, []

        def plan_callback(
            session_id: str,
            workflow_value: str | None,
            design_text: str,
            curve_id: str,
        ) -> tuple[str, dict[str, Any], str]:
            try:
                if not session_id or not workflow_value:
                    raise UIServiceError("会话和分析流程都必须显式选择。")
                result = service.generate_plan(
                    session_id,
                    workflow_value,
                    design=(
                        _json_object(design_text, "分析设计")
                        if workflow_value != "generic_grouped"
                        else None
                    ),
                    curve_run_id=curve_id.strip() or None,
                )
                return "计划已生成但尚未确认；生成不等于批准执行。", result, result["plan_sha256"]
            except UIServiceError as exc:
                message, payload = _error(exc)
                return f"计划生成未完成：{message}", payload, ""

        def confirm_callback(
            session_id: str,
            displayed_hash: str,
            confirmation_text: str,
            explicit: bool,
        ) -> tuple[str, str, str, dict[str, Any]]:
            try:
                result = service.confirm_plan(
                    session_id,
                    displayed_hash.strip(),
                    _json_object(confirmation_text, "警告确认"),
                    explicit_confirmation=explicit,
                )
                return (
                    "计划已确认；执行前后端仍会重新验证绑定。",
                    result["plan_sha256"],
                    result["plan_sha256"],
                    result,
                )
            except UIServiceError as exc:
                message, payload = _error(exc)
                return f"计划确认未完成：{message}", "", "", payload

        def execute_callback(session_id: str, confirmed_hash: str) -> tuple[str, dict[str, Any]]:
            try:
                result = service.execute_plan(session_id, confirmed_hash.strip())
                status = "分析已执行" if result["analysis_ready"] else "分析产生了明确的非成功状态"
                return status, result
            except UIServiceError as exc:
                message, payload = _error(exc)
                return f"分析未执行：{message}", payload

        def report_callback(
            session_id: str, report_kind: str | None, run_id: str, inverse_id: str
        ) -> tuple[str, dict[str, Any]]:
            try:
                if not report_kind or not run_id.strip():
                    raise UIServiceError("报告类型和来源 run_id 都必须显式填写。")
                result = service.render_report(
                    session_id,
                    report_kind,
                    run_id.strip(),
                    inverse_run_id=inverse_id.strip() or None,
                )
                return "报告已生成；文件仅限当前会话下载。", result
            except UIServiceError as exc:
                message, payload = _error(exc)
                return f"报告未生成：{message}", payload

        def download_callback(
            session_id: str, relative: str
        ) -> tuple[str, str | None]:
            try:
                path = service.download_path(session_id, relative.strip())
                return "文件已通过当前会话范围校验，可以下载。", str(path)
            except UIServiceError as exc:
                return f"下载未完成：{exc.message}", None

        demo.load(start_session, outputs=[session_state, session_text, session_status])
        list_sheets_button.click(list_sheets, inputs=[upload], outputs=[sheet_result])
        import_button.click(
            import_callback,
            inputs=[session_state, upload, assay, mapping, sheet, encoding, delimiter],
            outputs=[import_status, import_result, import_preview],
        )
        generate_button.click(
            plan_callback,
            inputs=[session_state, workflow, design, curve_run_id],
            outputs=[plan_status, plan_payload, plan_hash],
        )
        confirm_button.click(
            confirm_callback,
            inputs=[session_state, plan_hash, warning_confirmations, explicit_confirmation],
            outputs=[plan_status, plan_hash, plan_hash_state, plan_payload],
        )
        execute_button.click(
            execute_callback,
            inputs=[session_state, plan_hash_state],
            outputs=[execute_status, execute_payload],
        )
        report_button.click(
            report_callback,
            inputs=[session_state, report_type, report_run_id, inverse_report_run_id],
            outputs=[report_status, report_payload],
        )
        download_button.click(
            download_callback,
            inputs=[session_state, download_relative],
            outputs=[download_status, download_file],
        )
    return demo


__all__ = ["build_app"]
