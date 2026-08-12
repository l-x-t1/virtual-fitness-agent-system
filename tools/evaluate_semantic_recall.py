from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.embeddings import SemanticEmbeddings


DOCUMENTS = [
    {"id": "knee_low_impact", "text": "膝盖不适 低冲击训练 快走 骑行 椭圆机 避免跳跃 保护关节"},
    {"id": "beginner_safe_plan", "text": "新手 入门 循序渐进 一周两到三练 安全训练计划"},
    {"id": "fat_loss_low_impact", "text": "减脂 减肥 体重较大 低冲击有氧 控制热量 快走骑行"},
    {"id": "home_core", "text": "居家 宿舍 无器械 核心训练 死虫 鸟狗 卷腹"},
    {"id": "plank_core", "text": "平板支撑 核心稳定 收紧腹部 避免塌腰 呼吸"},
    {"id": "back_safe_training", "text": "腰痛 腰部不适 核心稳定 避免塌腰 髋铰链保护腰椎"},
    {"id": "warmup_dynamic", "text": "训练前 热身 动态拉伸 髋膝踝活动 跑步准备"},
    {"id": "short_evening_plan", "text": "晚上 下班后 二十分钟 短时训练 高效计划"},
    {"id": "weekly_plan", "text": "训练频率 一周三练 隔天恢复 力量有氧结合"},
    {"id": "indoor_cardio", "text": "室内有氧 下雨 空气不好 原地踏步 动感单车 椭圆机"},
    {"id": "air_quality_safety", "text": "空气质量 雾霾 室外训练风险 改为室内训练"},
    {"id": "shoulder_safe_upper", "text": "肩膀不适 上肢训练 肩关节保护 弹力带 外旋"},
    {"id": "muscle_strength", "text": "增肌 力量训练 深蹲 推 拉 大肌群 渐进负荷"},
    {"id": "gym_equipment_strength", "text": "健身房 器械 杠铃 哑铃 坐姿划船 练背 力量"},
    {"id": "recovery_soreness", "text": "训练后 酸痛 恢复 睡眠 补水 蛋白质 轻活动"},
    {"id": "hip_mobility", "text": "久坐 髋部紧张 髋屈肌 拉伸 灵活性 活动度"},
    {"id": "squat_knee_form", "text": "深蹲 膝盖 脚尖方向一致 下肢动作标准"},
    {"id": "body_shaping", "text": "塑形 女性 基础动作 臀腿核心 力量训练"},
    {"id": "ankle_safe", "text": "脚踝旧伤 踝关节 避免跳绳 跳跃 低冲击替代"},
    {"id": "flexibility_stretch", "text": "柔韧性 拉伸 放松 呼吸 训练后静态拉伸"},
    {"id": "recovery_safe_return", "text": "恢复期 伤后复训 避免二次受伤 降低强度"},
    {"id": "nutrition_timing", "text": "训练前饮食 饭后间隔 消化 碳水 蛋白质 补给"},
]


class LegacyHashingEmbeddings:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        return _normalize(vector)

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        words = re.findall(r"[a-z0-9_]+", lowered)
        chinese = "".join(char for char in lowered if "\u4e00" <= char <= "\u9fff")
        chars = list(chinese)
        bigrams = [chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))]
        return words + chars + bigrams


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return vector if norm == 0 else [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def rank(embedding, query: str, top_k: int) -> list[str]:
    query_vector = embedding.embed_query(query)
    doc_vectors = embedding.embed_documents([item["text"] for item in DOCUMENTS])
    scored = [
        (_cosine(query_vector, vector), item["id"])
        for item, vector in zip(DOCUMENTS, doc_vectors)
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [doc_id for _, doc_id in scored[:top_k]]


def evaluate(cases: list[dict], embedding, top_k: int = 3) -> dict:
    hits = 0
    rows = []
    for case in cases:
        ranked = rank(embedding, case["query"], top_k)
        expected = set(case["expected_ids"])
        ok = bool(expected.intersection(ranked))
        hits += int(ok)
        rows.append({"query": case["query"], "expected": sorted(expected), "top_ids": ranked, "hit": ok})
    return {"recall_at_k": round(hits / len(cases), 4), "hits": hits, "total": len(cases), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy hashing recall with semantic embeddings.")
    parser.add_argument("--cases", default="tests/fixtures/fitness_semantic_recall_cases.json")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cases = json.loads((ROOT / args.cases).read_text(encoding="utf-8"))
    legacy = evaluate(cases, LegacyHashingEmbeddings(), args.top_k)
    semantic = evaluate(cases, SemanticEmbeddings(), args.top_k)
    payload = {"top_k": args.top_k, "legacy_hashing": legacy, "semantic": semantic}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Recall@{args.top_k} legacy hashing: {legacy['hits']}/{legacy['total']} = {legacy['recall_at_k']}")
    print(f"Recall@{args.top_k} semantic:       {semantic['hits']}/{semantic['total']} = {semantic['recall_at_k']}")


if __name__ == "__main__":
    main()
