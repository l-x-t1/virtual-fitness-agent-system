from __future__ import annotations

import json
import re
from typing import Any

from app.ai.knowledge_base import FitnessKnowledgeBase
from app.ai.memory import ConversationStore
from app.ai.prompts import CORRECTION, PLAN, PROFILE, QA, SYSTEM_COACH
from app.ai.rag import HybridRAGPipeline
from app.ai.schemas import TrainingPlan, UserProfile
from app.agents.output_parser import OutputParser
from app.llm import LLMClient, LLMError
from app.observability import get_tracer


class AICoach:
    def __init__(self, llm=None, memory=None, knowledge=None, rag=None, tracer=None):
        self.llm = llm or LLMClient()
        self.memory = memory or ConversationStore()
        self.knowledge = knowledge or FitnessKnowledgeBase()
        self.tracer = tracer or get_tracer()
        self.rag = rag or HybridRAGPipeline(
            knowledge_base=self.knowledge,
            llm=self.llm,
            tracer=self.tracer,
        )
        self.parser = OutputParser()

    def status(self) -> dict:
        providers = self.llm.available()
        return {
            "ready": True,
            "mode": "online" if any(item["configured"] for item in providers) else "demo",
            "providers": providers,
            "knowledge_documents": len(self.knowledge.documents),
            "speech": {"recognition": "browser", "synthesis": "browser"},
            "session_storage": "sqlite",
            "knowledge": self.knowledge.stats(),
        }

    def test_provider(self, provider: str, model: str | None = None) -> dict:
        try:
            return self.llm.test_connection(provider, model)
        except LLMError as exc:
            config = self.llm.resolve(provider, model)
            return {"ok": False, "provider": config.name, "model": config.model, "error": str(exc)}

    def create_session(self, user_id: int, title: str | None = None) -> dict:
        item = self.memory.create(user_id, title or "新的训练对话")
        return self._session(item)

    def sessions(self, user_id: int) -> list[dict]:
        return [self._session(item) for item in self.memory.list(user_id)]

    def session(self, user_id: int, session_id: str) -> dict | None:
        item = self.memory.get(session_id, user_id)
        return self._session(item, include_messages=True) if item else None

    def delete_session(self, user_id: int, session_id: str) -> bool:
        return self.memory.delete(session_id, user_id)

    def chat(self, user: dict, history: list[dict], data: dict) -> dict:
        prepared = self.prepare_chat(user, history, data)
        return self.complete_chat(prepared, data)

    def prepare_chat(self, user: dict, history: list[dict], data: dict, trace=None) -> dict:
        session = self.memory.get(data["session_id"], user["id"])
        if not session:
            raise ValueError("AI 会话不存在或已过期")
        question = data["message"].strip()
        trace = trace or self.tracer.start_trace(
            "ai_chat",
            session_id=session.id,
            user_id=user["id"],
            metadata={
                "agent": "AICoach",
                "prompt_template": "hybrid_rag_grounded_answer",
                "provider": data.get("provider"),
                "model": data.get("model"),
                "user_input": question,
            },
        )
        with trace.span("memory.read", component="memory"):
            memory_context = self.memory.context(user["id"], session=session, query=question)
        trace.event(
            "memory.context",
            {
                "short_term_messages": len(memory_context.short_term_messages),
                "long_term_hits": len(memory_context.long_term_memories),
                "summary_hits": len(memory_context.summary_memories),
            },
        )
        profile = self.profile(user, history, use_llm=False)
        profile = self._merge_memory_into_profile(profile, memory_context.long_term_memories)
        retrieval = self.rag.retrieve(
            question,
            recent_messages=memory_context.short_term_messages,
            memory=memory_context,
            user_id=user["id"],
            provider=data.get("provider"),
            model=data.get("model"),
            top_k=5,
            trace=trace,
        )
        return {
            "session": session,
            "question": question,
            "memory_context": memory_context,
            "profile": profile,
            "retrieval": retrieval,
            "trace": trace,
            "user": user,
            "history": history,
        }

    def complete_chat(
        self,
        prepared: dict,
        data: dict,
        *,
        answer_override: str | None = None,
        mode_override: str | None = None,
    ) -> dict:
        session = prepared["session"]
        question = prepared["question"]
        memory_context = prepared["memory_context"]
        trace = prepared["trace"]
        rag_result = self.rag.complete(
            question,
            prepared["retrieval"],
            provider=data.get("provider"),
            model=data.get("model"),
            trace=trace,
            answer_override=answer_override,
            mode_override=mode_override,
            finish_trace=False,
        )
        answer = rag_result.answer
        mode = "online" if rag_result.mode == "online" else "demo"
        self.memory.add(session, "user", question)
        self.memory.add(session, "assistant", answer)
        if len(session.messages) == 2 and (
            session.title in {"新的训练对话", "训练咨询"} or session.title.startswith("新对话 ")
        ):
            session.title = question[:16] + ("…" if len(question) > 16 else "")
        session.state["last_topic"] = question[:80]
        session.state["turn_count"] = int(session.state.get("turn_count", 0)) + 1
        try:
            resolved_provider = data.get("provider") or self.llm.resolve().name
        except Exception:
            resolved_provider = data.get("provider") or "unknown"
        session.state["last_provider"] = resolved_provider
        self.memory.save(session)
        with trace.span("memory.write", component="memory"):
            memory_update = self.memory.remember_turn(
                user_id=prepared["user"]["id"],
                session=session,
                user_message=question,
                assistant_message=answer,
                llm=self.llm,
                provider=data.get("provider"),
                model=data.get("model"),
            )
        result = {
            "session_id": session.id,
            "answer": answer,
            "mode": mode,
            "sources": rag_result.sources,
            "citations": rag_result.citations,
            "trace_id": rag_result.trace_id,
            "retrieval": {
                "queries": rag_result.rewritten_queries,
                "counts": rag_result.retrieval_counts,
                "rewrite_mode": rag_result.rewrite_mode,
                "rerank_mode": rag_result.rerank_mode,
            },
            "state": dict(session.state),
            "memory": {
                "short_term_messages": len(memory_context.short_term_messages),
                "long_term_hits": len(memory_context.long_term_memories),
                "summary_hits": len(memory_context.summary_memories),
                "long_term_saved": memory_update["long_term_saved"],
                "summary_updated": memory_update["summary_updated"],
            },
        }
        trace.finish({"mode": mode, "source_count": len(rag_result.sources)})
        return result

    def profile(self, user: dict, history: list[dict], use_llm: bool = True, provider=None, model=None) -> dict:
        payload = {"body_data": user, "training_history": history}
        if use_llm:
            try:
                raw = self.llm.chat(
                    [{"role": "system", "content": SYSTEM_COACH}, {"role": "user", "content": PROFILE.replace("{input_json}", json.dumps(payload, ensure_ascii=False, default=str))}],
                    provider,
                    model,
                )
                return UserProfile.model_validate(self.parser.loads(raw)).model_dump()
            except (LLMError, ValueError):
                pass
        metrics = self._profile_metrics(history)
        level = user.get("fitness_level") or (
            "beginner" if metrics["session_count"] < 4 else "intermediate" if metrics["average_score"] < 88 else "advanced"
        )
        injuries = str(user.get("injuries") or "").strip()
        preference = str(user.get("preference") or "综合训练").strip()
        strengths = [f"{metrics['best_exercise']}表现较好"] if metrics.get("best_exercise") else []
        improvement = [f"优先改善{metrics['weak_exercise']}动作质量"] if metrics.get("weak_exercise") else ["先建立稳定训练频率"]
        habit_text = (
            [
                f"近期共训练 {metrics['session_count']} 次",
                f"平均每周约 {metrics['weekly_frequency']} 次",
                f"累计训练 {metrics['total_minutes']} 分钟",
                f"成绩趋势：{metrics['score_trend']}",
            ]
            if history
            else ["尚未形成稳定训练记录"]
        )
        return UserProfile(
            fitness_level=level,
            goals=["稳定完成每周训练", "逐步提升动作质量"],
            preferences=[preference],
            risk_flags=[injuries] if injuries and injuries not in {"无", "暂无"} else [],
            habits=habit_text,
            strengths=strengths,
            improvement_areas=improvement,
            metrics=metrics,
            summary=(
                f"{user.get('nickname', '用户')}当前体能等级为{level}，偏好{preference}；"
                f"近期平均分{metrics['average_score']}，每周约训练{metrics['weekly_frequency']}次。"
            ),
        ).model_dump()

    def plan(self, user: dict, history: list[dict], data: dict) -> dict:
        profile = self.profile(user, history, use_llm=False)
        memory_context = self.memory.context(user["id"], query=str(data.get("goal") or "训练计划"))
        profile = self._merge_memory_into_profile(profile, memory_context.long_term_memories)
        payload = {
            "profile": profile,
            "history": history[:10],
            "request": data,
            "memory_context": memory_context.as_system_prompt(),
        }
        try:
            raw = self.llm.chat(
                [{"role": "system", "content": SYSTEM_COACH}, {"role": "user", "content": PLAN.replace("{input_json}", json.dumps(payload, ensure_ascii=False, default=str))}],
                data.get("provider"),
                data.get("model"),
            )
            plan = TrainingPlan.model_validate(self.parser.loads(raw)).model_dump()
            return {"plan": plan, "mode": "online", "profile": profile}
        except (LLMError, ValueError):
            return {"plan": self._demo_plan(profile, data), "mode": "demo", "profile": profile}

    def correct(self, user: dict, data: dict) -> dict:
        payload = {"user": user, **data}
        try:
            answer = self.llm.chat(
                [{"role": "system", "content": SYSTEM_COACH}, {"role": "user", "content": CORRECTION.format(input_json=json.dumps(payload, ensure_ascii=False))}],
                data.get("provider"),
                data.get("model"),
            )
            mode = "online"
        except LLMError:
            score = data.get("score", 0)
            answer = "动作整体稳定，继续保持核心收紧和匀速呼吸。" if score >= 80 else "请降低速度，保持关节方向稳定，在无痛范围内完成动作。"
            mode = "demo"
        return {"feedback": answer, "mode": mode}

    def _demo_answer(self, question: str, context: list[dict], profile: dict) -> str:
        sources = [item["content"] for item in context[:2]]
        source = " ".join(sources) if sources else "训练应循序渐进，并以动作质量和安全为先。"
        risk = profile.get("risk_flags") or []
        if re.search(r"痛|疼|晕|胸闷|呼吸困难", question):
            return "先暂停当前动作。若是急性剧痛、胸痛、晕厥或异常呼吸困难，请及时寻求专业帮助；普通持续疼痛也应由专业人员评估。"
        if re.search(r"体脂|减脂|减肥|瘦", question):
            return "降低体脂的核心是形成可持续的能量缺口，同时尽量保留肌肉：\n1. 优先调整总热量和蛋白质摄入。\n2. 每周安排2到4次力量训练，并保留适量有氧。\n3. 保证睡眠和日常活动量。\n4. 用2到4周趋势评估，不追求短期快速下降。"
        if re.search(r"每周|几次|频率|多久练", question):
            level = profile.get("fitness_level", "beginner")
            return ("如果你目前是新手，建议从每周2到3次全身训练开始，每次间隔至少1天。"
                    "连续2到4周能稳定完成且恢复良好后，再增加到每周3到4次；不要同时大幅增加次数、时长和强度。")
        if re.search(r"深蹲|俯卧撑|平板|动作|姿势|怎么做", question):
            return f"动作质量优先于次数。{source} 练习时可先慢速完成一组，用无痛、稳定、可重复作为进阶标准。"
        if re.search(r"吃|饮食|蛋白|碳水", question):
            return "饮食应围绕可持续和训练恢复安排：每餐包含优质蛋白，搭配蔬菜和适量主食；训练前后不必极端忌口，重点关注全天总摄入。"
        if re.search(r"休息|恢复|疲劳|睡眠", question):
            return f"{source} 如果连续数次训练表现下降、睡眠变差或疲劳持续，应减少训练量并增加恢复日。"
        risk_note = f" 你的画像记录了“{'、'.join(risk)}”，相关动作应优先采用低冲击替代。" if risk else ""
        return f"针对这个问题，可先采用以下原则：{source}{risk_note}"

    def _profile_metrics(self, history: list[dict]) -> dict:
        if not history:
            return {
                "session_count": 0,
                "average_score": 0,
                "weekly_frequency": 0,
                "total_minutes": 0,
                "best_exercise": "",
                "weak_exercise": "",
                "score_trend": "暂无数据",
            }
        scores = [float(item.get("score") or 0) for item in history]
        durations = [float(item.get("duration") or 0) for item in history]
        exercise_scores: dict[str, list[float]] = {}
        for item, score in zip(history, scores):
            exercise_scores.setdefault(str(item.get("exercise_name") or "未知动作"), []).append(score)
        averages = {name: sum(values) / len(values) for name, values in exercise_scores.items()}
        dates = []
        for item in history:
            raw = item.get("created_at")
            try:
                dates.append(__import__("datetime").datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
            except (TypeError, ValueError):
                pass
        span_days = max(7, ((max(dates) - min(dates)).days + 1) if len(dates) >= 2 else 7)
        recent = scores[: min(3, len(scores))]
        older = scores[-min(3, len(scores)) :]
        delta = (sum(recent) / len(recent)) - (sum(older) / len(older))
        trend = "上升" if delta >= 3 else "下降" if delta <= -3 else "稳定"
        return {
            "session_count": len(history),
            "average_score": round(sum(scores) / len(scores), 1),
            "weekly_frequency": round(len(history) / span_days * 7, 1),
            "total_minutes": round(sum(durations) / 60, 1),
            "best_exercise": max(averages, key=averages.get),
            "weak_exercise": min(averages, key=averages.get),
            "score_trend": trend,
        }

    def _demo_plan(self, profile: dict, data: dict) -> dict:
        minutes = max(10, min(int(data.get("duration_minutes") or 25), 60))
        low_impact = bool(profile.get("risk_flags"))
        exercises = [
            {"name": "徒手深蹲" if not low_impact else "椅子辅助深蹲", "sets": 2, "reps": "8-12次", "rest_seconds": 45, "intensity": "低到中等", "notes": "膝盖与脚尖方向一致"},
            {"name": "跪姿俯卧撑", "sets": 2, "reps": "6-10次", "rest_seconds": 45, "intensity": "低到中等", "notes": "保持躯干稳定"},
            {"name": "鸟狗式", "sets": 2, "reps": "每侧8次", "rest_seconds": 30, "intensity": "低强度", "notes": "动作缓慢，避免躯干旋转"},
        ]
        return TrainingPlan(
            title="AI 教练个性化训练卡",
            goal=str(data.get("goal") or "提升基础体能与动作稳定性"),
            duration_minutes=minutes,
            warmup=["原地踏步 3 分钟", "肩髋动态活动 2 分钟"],
            exercises=exercises,
            cooldown=["慢走与调整呼吸", "轻柔拉伸主要训练肌群"],
            safety_notes=["全程保持无痛且可控", "不适时立即降低强度或停止"],
        ).model_dump()

    def _merge_memory_into_profile(self, profile: dict, memories: list[dict]) -> dict:
        enriched = dict(profile or {})
        goals = list(enriched.get("goals") or [])
        preferences = list(enriched.get("preferences") or [])
        risk_flags = list(enriched.get("risk_flags") or [])
        habits = list(enriched.get("habits") or [])
        memory_notes = []

        for item in memories:
            category = str(item.get("category") or "")
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            memory_notes.append(content)
            if category == "body_issue" and content not in risk_flags:
                risk_flags.append(content)
            elif category == "goal" and content not in goals:
                goals.append(content)
            elif category == "preference" and content not in preferences:
                preferences.append(content)
            elif category == "habit" and content not in habits:
                habits.append(content)
            elif category == "age":
                match = re.search(r"\d{1,3}", content)
                if match:
                    enriched["age"] = int(match.group(0))

        enriched["goals"] = goals
        enriched["preferences"] = preferences
        enriched["risk_flags"] = risk_flags
        enriched["habits"] = habits
        if memory_notes:
            summary = str(enriched.get("summary") or "").strip()
            note = "记忆补充：" + "；".join(memory_notes[:6])
            enriched["summary"] = f"{summary} {note}".strip()
        return enriched

    def _session(self, item, include_messages: bool = False) -> dict:
        result = {
            "id": item.id,
            "title": item.title,
            "message_count": len(item.messages),
            "state": dict(item.state),
            "updated_at": item.updated_at.isoformat(),
        }
        if include_messages:
            result["messages"] = list(item.messages)
        return result
