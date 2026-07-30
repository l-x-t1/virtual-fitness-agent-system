from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from app.agents.base import BaseAgent
from app.agents.schemas import ReportOutput

ReportType = Literal["weekly", "monthly"]


class ReportAgent(BaseAgent):
    prompt_module = "app.agents.prompts.report_prompt"
    output_schema = ReportOutput

    def build_report(
        self,
        training_records: list[dict[str, Any]] | None,
        report_type: ReportType = "weekly",
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report_type = self._report_type(report_type)
        records = self._period_records(list(training_records or []), report_type)
        if not records:
            return self._empty_report(report_type)
        metrics = self._metrics(records)
        payload = {
            "report_type": report_type,
            "profile": dict(profile or {}),
            "metrics": metrics,
            "history": records,
        }
        try:
            result = self.run(payload)
            report = self._enforce_facts(result, report_type, metrics)
            return {**report, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {
                **self._fallback_report(report_type, metrics),
                **self.fallback_metadata(exc),
            }

    async def abuild_report(
        self,
        training_records: list[dict[str, Any]] | None,
        report_type: ReportType = "weekly",
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report_type = self._report_type(report_type)
        records = self._period_records(list(training_records or []), report_type)
        if not records:
            return self._empty_report(report_type)
        metrics = self._metrics(records)
        payload = {
            "report_type": report_type,
            "profile": dict(profile or {}),
            "metrics": metrics,
            "history": records,
        }
        try:
            result = await self.arun(payload)
            report = self._enforce_facts(result, report_type, metrics)
            return {**report, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {
                **self._fallback_report(report_type, metrics),
                **self.fallback_metadata(exc),
            }

    def _metrics(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        chronological = self._chronological(records)
        scores = [self._number(item.get("score")) for item in chronological]
        durations = [
            self._number(item.get("duration_minutes", item.get("duration", 0)))
            for item in chronological
        ]
        by_exercise: dict[str, list[float]] = defaultdict(list)
        for item, score in zip(chronological, scores):
            name = str(item.get("exercise_name") or item.get("name") or "").strip()
            if name:
                by_exercise[name].append(score)
        averages = {
            name: sum(values) / len(values)
            for name, values in by_exercise.items()
        }
        ranked = sorted(averages, key=lambda name: (-averages[name], name))
        strengths = ranked[:1]
        weaknesses = ranked[-1:] if len(ranked) > 1 else []
        if len(scores) < 2:
            trend = "insufficient"
        else:
            midpoint = max(1, len(scores) // 2)
            earlier = sum(scores[:midpoint]) / midpoint
            later_values = scores[midpoint:]
            later = sum(later_values) / len(later_values)
            if later > earlier + 2:
                trend = "improving"
            elif later < earlier - 2:
                trend = "declining"
            else:
                trend = "stable"
        return {
            "training_count": len(records),
            "average_score": round(sum(scores) / len(scores), 1),
            "total_duration": round(sum(durations), 1),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "trend": trend,
            "exercise_names": list(by_exercise),
        }

    def _chronological(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not all(item.get("created_at") is not None for item in records):
            return records
        return sorted(records, key=lambda item: str(item.get("created_at")))

    def _period_records(
        self,
        records: list[dict[str, Any]],
        report_type: ReportType,
    ) -> list[dict[str, Any]]:
        days = 7 if report_type == "weekly" else 30
        filtered = []
        for item in records:
            raw_date = item.get("created_at")
            if raw_date in (None, ""):
                filtered.append(item)
                continue
            try:
                if isinstance(raw_date, datetime):
                    created_at = raw_date
                else:
                    created_at = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                now = datetime.now(tz=created_at.tzinfo)
            except (TypeError, ValueError):
                # Unknown date formats are caller data, not evidence that the
                # record is outside the requested period.
                filtered.append(item)
                continue
            if created_at >= now - timedelta(days=days):
                filtered.append(item)
        return filtered

    def _enforce_facts(
        self,
        generated: dict[str, Any],
        report_type: ReportType,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        allowed = set(metrics["exercise_names"])
        generated = dict(generated)
        generated.update(
            {
                "report_type": report_type,
                "empty": False,
                "training_count": metrics["training_count"],
                "average_score": metrics["average_score"],
                "total_duration": metrics["total_duration"],
                "strengths": [
                    name for name in generated.get("strengths", []) if name in allowed
                ] or metrics["strengths"],
                "weaknesses": [
                    name for name in generated.get("weaknesses", []) if name in allowed
                ] or metrics["weaknesses"],
            }
        )
        return ReportOutput.model_validate(generated).model_dump()

    def _fallback_report(
        self,
        report_type: ReportType,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        period = "本周" if report_type == "weekly" else "本月"
        trend_map = {
            "improving": "后半段平均分高于前半段，当前记录显示上升趋势。",
            "declining": "后半段平均分低于前半段，应优先检查训练负荷与动作质量。",
            "stable": "前后阶段平均分接近，表现整体稳定。",
            "insufficient": "训练记录不足，暂时无法判断趋势。",
        }
        reminders = []
        if metrics["average_score"] < 60:
            reminders.append("平均动作评分偏低，下一阶段优先保证动作质量并降低训练难度。")
        plan = [f"下一{'周' if report_type == 'weekly' else '月'}保持规律训练并记录每次动作评分。"]
        if metrics["weaknesses"]:
            plan.append(f"针对{metrics['weaknesses'][0]}安排低强度分解练习。")
        report = ReportOutput(
            report_type=report_type,
            empty=False,
            training_count=metrics["training_count"],
            average_score=metrics["average_score"],
            total_duration=metrics["total_duration"],
            strengths=metrics["strengths"],
            weaknesses=metrics["weaknesses"],
            trend_analysis=trend_map[metrics["trend"]],
            risk_reminders=reminders,
            next_plan=plan,
            summary=(
                f"{period}完成 {metrics['training_count']} 次训练，"
                f"平均分 {metrics['average_score']}，总时长 {metrics['total_duration']}。"
            ),
        )
        return report.model_dump()

    def _empty_report(self, report_type: ReportType) -> dict[str, Any]:
        period = "本周" if report_type == "weekly" else "本月"
        report = ReportOutput(
            report_type=report_type,
            empty=True,
            training_count=0,
            average_score=0,
            total_duration=0,
            strengths=[],
            weaknesses=[],
            trend_analysis="没有训练记录，无法分析趋势。",
            risk_reminders=[],
            next_plan=["完成首次训练并记录动作评分与时长。"],
            summary=f"{period}暂无训练记录。",
        )
        return {
            **report.model_dump(),
            **self.fallback_metadata(reason="no_training_records"),
        }

    def _report_type(self, value: str) -> ReportType:
        if value not in {"weekly", "monthly"}:
            raise ValueError("report_type must be 'weekly' or 'monthly'.")
        return value

    def _number(self, value: Any) -> float:
        try:
            return max(0.0, float(value or 0))
        except (TypeError, ValueError):
            return 0.0
