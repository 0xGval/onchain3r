"""Report generator - markdown and JSON output."""

from __future__ import annotations

import json

from onchain3r.core.models import DueDiligenceReport


def to_markdown(report: DueDiligenceReport) -> str:
    lines = [
        f"# Due Diligence Report",
        f"**Token:** `{report.token_address}`  ",
        f"**Chain:** {report.chain}  ",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M UTC}  ",
        f"**Risk Score:** {report.overall_risk_score}/10 ({report.overall_risk_level.value.upper()})",
        "",
        "---",
        "",
        "## Overview",
        report.overview,
        "",
        "## On-chain Analysis",
        report.onchain_analysis,
        "",
        "## Social Analysis",
        report.social_analysis,
        "",
        "## Risk Breakdown",
        "",
    ]

    for cat in report.risk_categories:
        lines.append(f"### {cat.name}")
        lines.append(f"**Score:** {cat.score}/10 ({cat.level.value})  ")
        lines.append(cat.details)
        lines.append("")

    if report.risk_factors:
        lines.append("## Risk Factors")
        for f in report.risk_factors:
            lines.append(f"- ⚠ {f}")
        lines.append("")

    if report.positive_signals:
        lines.append("## Positive Signals")
        for s in report.positive_signals:
            lines.append(f"- ✓ {s}")
        lines.append("")

    lines.extend(["## Verdict", report.verdict, ""])
    return "\n".join(lines)


def to_json(report: DueDiligenceReport) -> str:
    return json.dumps(
        report.model_dump(mode="json", exclude={"raw_data"}),
        indent=2,
        default=str,
    )
