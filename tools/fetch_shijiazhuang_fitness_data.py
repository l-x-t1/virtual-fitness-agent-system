from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SHIJIAZHUANG_CENTER = {"city": "石家庄", "latitude": 38.0428, "longitude": 114.5149}

EXERCISE_LIBRARY_SEED = [
    {"name": "动态热身", "category": "热身", "intensity": "低", "duration_min": "5", "target_body_part": "全身"},
    {"name": "快走", "category": "有氧", "intensity": "低到中", "duration_min": "20", "target_body_part": "全身"},
    {"name": "深蹲", "category": "力量", "intensity": "中", "duration_min": "10", "target_body_part": "下肢"},
    {"name": "平板支撑", "category": "核心", "intensity": "中", "duration_min": "5", "target_body_part": "核心"},
]

BMI_RULES = [
    {"standard": "China adult", "category": "偏瘦", "min_bmi": "0", "max_bmi": "18.49", "risk_hint": "循序渐进训练。"},
    {"standard": "China adult", "category": "正常", "min_bmi": "18.5", "max_bmi": "23.99", "risk_hint": "可安排有氧和力量训练。"},
    {"standard": "China adult", "category": "超重", "min_bmi": "24", "max_bmi": "27.99", "risk_hint": "优先低冲击有氧。"},
    {"standard": "China adult", "category": "肥胖", "min_bmi": "28", "max_bmi": "99", "risk_hint": "避免突然高强度冲刺。"},
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_seed(output_dir: Path) -> None:
    ensure_dir(output_dir)
    write_csv(output_dir / "exercise_library_seed.csv", EXERCISE_LIBRARY_SEED, ["name", "category", "intensity", "duration_min", "target_body_part"])
    write_csv(output_dir / "bmi_rules.csv", BMI_RULES, ["standard", "category", "min_bmi", "max_bmi", "risk_hint"])
    write_csv(output_dir / "shijiazhuang_venues.csv", [], ["source", "city", "keyword", "venue_group", "poi_id", "name", "type", "address", "district", "longitude", "latitude", "rating", "suitable_sports"])
    write_json(output_dir / "manifest.json", {**SHIJIAZHUANG_CENTER, "exercise_seed_count": len(EXERCISE_LIBRARY_SEED), "bmi_rule_count": len(BMI_RULES), "note": "Generated CSV seed files only; application database writes are handled by ORM migration/import tools."})


def main():
    parser = argparse.ArgumentParser(description="Generate local Shijiazhuang fitness seed CSV files.")
    parser.add_argument("--output-dir", type=Path, default=Path("tools/data_seed/shijiazhuang"))
    args = parser.parse_args()
    build_seed(args.output_dir)
    print(f"Seed files written to {args.output_dir}")


if __name__ == "__main__":
    main()
