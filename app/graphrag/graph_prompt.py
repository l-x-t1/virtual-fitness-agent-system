"""Prompt templates for fitness GraphRAG answers."""

from __future__ import annotations


GRAPH_RAG_SYSTEM_PROMPT = """你是专业健身 AI 教练，回答必须基于给定知识图谱上下文。

要求：
1. 优先解释可能原因，再给出纠正方案。
2. 如果涉及疼痛、肿胀、麻木或持续不适，提醒用户停止训练并寻求专业评估。
3. 不编造上下文之外的动作、错误点或治疗结论。
4. 输出中文，结构清晰，适合 AI 教练服务直接展示。
"""


GRAPH_RAG_USER_PROMPT = """用户问题：
{question}

知识图谱上下文：
{context}

请输出：
- 可能原因
- 纠正建议
- 辅助训练
- 安全提醒
"""


def build_graph_rag_prompt(question: str, context: str) -> str:
    """Build the final prompt sent to the LangChain-backed LLM client."""
    return "\n\n".join(
        [
            GRAPH_RAG_SYSTEM_PROMPT.strip(),
            GRAPH_RAG_USER_PROMPT.format(question=question.strip(), context=context.strip()).strip(),
        ]
    )
