from __future__ import annotations

from ..models import ScenarioReport


def report_to_json(report: ScenarioReport) -> str:
    return report.model_dump_json(indent=2)


def report_to_markdown(report: ScenarioReport) -> str:
    lines = [f"# {report.title}", "", report.executive_summary, ""]
    lines.extend([
        f"- 场景：{report.scenario.scenario_type.value}",
        f"- 路由置信度：{report.scenario.confidence:.0%}",
        f"- 风险数：{len(report.risks)}",
        f"- 建议动作数：{len(report.actions)}",
        f"- 生成时间：{report.generated_at.isoformat()}",
        "",
        "## 风险",
        "",
    ])
    for risk in report.risks:
        lines.append(f"- {risk.level.value} {risk.risk_type.value}：{risk.material_id}/{risk.plant}，数量 {risk.quantity:.2f}，金额 {risk.value:.2f}")
    lines.extend(["", "## 动作与审批", ""])
    for action in report.actions:
        approval = "无需审批"
        if action.approval and action.approval.required:
            approval = f"待审批：{', '.join(action.approval.approvers)}"
        lines.append(f"- {action.action_type.value} {action.material_id} {action.quantity:.2f}；{approval}；截止 {action.due_date}")
    if report.limitations:
        lines.extend(["", "## 数据限制", "", *[f"- {item}" for item in report.limitations]])
    return "\n".join(lines)
