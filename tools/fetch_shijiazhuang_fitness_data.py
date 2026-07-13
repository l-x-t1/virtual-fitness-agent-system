"""
Fetch Shijiazhuang fitness reference data.

Outputs CSV files and a SQLite database under data_seed/shijiazhuang by default.

Data sources:
- AMap Web Service place search for Shijiazhuang fitness venues. Requires AMAP_KEY.
- Open-Meteo forecast and air-quality APIs for local weather / AQI context. No key.
- CDC NHANES public XPT files for anonymized body-measure reference. Requires pandas.
- Adult Compendium of Physical Activities pages for MET reference. No key.
- WHO / CDC guideline summaries encoded as reference rules.

This script only collects public reference data. It does not collect real user
age, injury history, height, weight, location, or training records.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


SHIJIAZHUANG_CENTER = {
    "city": "石家庄",
    "latitude": 38.0428,
    "longitude": 114.5149,
}

POI_KEYWORDS = {
    "gym": ["健身房", "健身中心", "瑜伽馆", "普拉提"],
    "sports_venue": ["体育馆", "运动场", "篮球馆", "羽毛球馆", "乒乓球馆", "游泳馆"],
    "outdoor": ["公园", "体育公园", "健身步道", "广场", "绿道"],
    "campus": ["大学体育馆", "学校操场"],
}

NHANES_DEMO_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_DEMO.XPT"
NHANES_BMX_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_BMX.XPT"

COMPENDIUM_URLS = [
    "https://pacompendium.com/walking/",
    "https://pacompendium.com/running/",
    "https://pacompendium.com/bicycling/",
    "https://pacompendium.com/conditioning-exercise/",
    "https://pacompendium.com/sports/",
    "https://pacompendium.com/water-activities/",
    "https://pacompendium.com/home-activities/",
]

BMI_RULES = [
    {"standard": "China adult", "category": "偏瘦", "min_bmi": "0", "max_bmi": "18.49", "risk_hint": "体重偏低，训练以基础力量、均衡营养和循序渐进为主。"},
    {"standard": "China adult", "category": "正常", "min_bmi": "18.5", "max_bmi": "23.99", "risk_hint": "BMI处于正常范围，可根据体能水平安排有氧和力量训练。"},
    {"standard": "China adult", "category": "超重", "min_bmi": "24", "max_bmi": "27.99", "risk_hint": "建议优先低冲击有氧和力量训练，逐步增加训练量。"},
    {"standard": "China adult", "category": "肥胖", "min_bmi": "28", "max_bmi": "99", "risk_hint": "运动风险较高，避免突然高强度冲刺和跳跃。"},
    {"standard": "WHO adult", "category": "Underweight", "min_bmi": "0", "max_bmi": "18.49", "risk_hint": "Underweight range."},
    {"standard": "WHO adult", "category": "Normal", "min_bmi": "18.5", "max_bmi": "24.99", "risk_hint": "Normal range."},
    {"standard": "WHO adult", "category": "Overweight", "min_bmi": "25", "max_bmi": "29.99", "risk_hint": "Overweight range."},
    {"standard": "WHO adult", "category": "Obesity", "min_bmi": "30", "max_bmi": "99", "risk_hint": "Obesity range."},
]

TRAINING_DURATION_RULES = [
    {
        "population": "adult",
        "risk_level": "low",
        "weekly_minutes": "150-300中等强度有氧，或75-150高强度有氧",
        "strength_days": "每周至少2天",
        "single_session_minutes": "30-60",
        "intensity": "中等，可按体能加入较高强度",
        "source": "WHO / CDC physical activity guidelines",
    },
    {
        "population": "adult",
        "risk_level": "medium",
        "weekly_minutes": "从90-150分钟逐步增加到150分钟以上",
        "strength_days": "每周1-2天，从低负荷开始",
        "single_session_minutes": "20-40",
        "intensity": "低到中等，避免突然冲刺",
        "source": "WHO / CDC physical activity guidelines + project safety rule",
    },
    {
        "population": "adult",
        "risk_level": "high",
        "weekly_minutes": "以10-20分钟短时低强度活动起步",
        "strength_days": "以康复、关节活动和轻阻力为主",
        "single_session_minutes": "10-20",
        "intensity": "低强度，建议先咨询医生或专业教练",
        "source": "Project safety rule based on public activity guidelines",
    },
]

TRAINING_ENVIRONMENT_RULES = [
    {
        "rule_code": "good_outdoor",
        "condition": "US AQI <= 50 且无明显降水",
        "recommendation": "适合室外中低强度有氧、快走、慢跑、骑行和公园训练。",
        "suitable_location": "公园,操场,绿道,室外场馆",
        "avoid_tags": "",
    },
    {
        "rule_code": "moderate_air",
        "condition": "50 < US AQI <= 100",
        "recommendation": "可进行低到中等强度训练，敏感人群建议缩短室外时长。",
        "suitable_location": "室内场馆,健身房,低强度室外",
        "avoid_tags": "高强度间歇,长距离跑",
    },
    {
        "rule_code": "poor_air",
        "condition": "US AQI > 100 或 PM2.5 偏高",
        "recommendation": "优先推荐室内训练、拉伸、核心稳定和低冲击力量训练。",
        "suitable_location": "健身房,居家,室内场馆",
        "avoid_tags": "室外高强度,长时间户外",
    },
    {
        "rule_code": "rain_or_wind",
        "condition": "降水明显或风速较高",
        "recommendation": "减少室外训练，推荐室内体感关卡、瑜伽拉伸、力量循环。",
        "suitable_location": "居家,健身房,室内场馆",
        "avoid_tags": "室外跑步,骑行",
    },
]

INJURY_AVOIDANCE_RULES = [
    {"injury_code": "none", "injury_name": "无明显伤病", "avoid_tags": "", "safe_tags": "综合训练,渐进训练", "note": "按体能等级控制训练量。"},
    {"injury_code": "knee", "injury_name": "膝关节不适", "avoid_tags": "跳跃,冲刺,深蹲过深,急停变向", "safe_tags": "低冲击有氧,骑行,游泳,上肢力量,核心稳定", "note": "避免膝盖内扣和大冲击落地。"},
    {"injury_code": "ankle", "injury_name": "踝关节不适", "avoid_tags": "跳跃,冲刺,敏捷折返,不平路面跑", "safe_tags": "低冲击有氧,坐姿训练,平衡恢复", "note": "控制落地冲击，优先稳定性训练。"},
    {"injury_code": "back", "injury_name": "腰背不适", "avoid_tags": "大重量硬拉,快速卷腹,负重扭转,高冲击跳跃", "safe_tags": "核心稳定,鸟狗式,臀桥,轻阻力训练", "note": "保持脊柱中立，避免疼痛范围动作。"},
    {"injury_code": "shoulder", "injury_name": "肩部不适", "avoid_tags": "过头推举,大重量引体,高速挥臂", "safe_tags": "下肢训练,轻阻力肩袖稳定,拉伸", "note": "肩痛时降低幅度和负荷。"},
    {"injury_code": "wrist", "injury_name": "腕部不适", "avoid_tags": "俯卧撑,长时间平板支撑,杠铃支撑", "safe_tags": "下肢训练,前臂中立支撑,器械替代", "note": "减少腕关节承重。"},
    {"injury_code": "cardio", "injury_name": "心肺相关风险", "avoid_tags": "高强度间歇,冲刺,长时间高心率", "safe_tags": "低强度步行,呼吸训练,短时活动", "note": "建议在医生或专业人员建议下训练。"},
]

EXERCISE_LIBRARY_SEED = [
    {"name": "动态热身", "category": "热身", "preference_type": "综合训练", "location_type": "居家,健身房,操场,公园", "intensity": "低", "met": "2.5", "duration_min": "5", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium,high", "goal_tags": "热身,激活"},
    {"name": "快走", "category": "有氧", "preference_type": "跑步,综合训练", "location_type": "公园,操场,绿道,室外", "intensity": "低到中", "met": "3.5", "duration_min": "20", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium,high", "goal_tags": "心肺,减脂,低冲击"},
    {"name": "慢跑", "category": "有氧", "preference_type": "跑步", "location_type": "操场,公园,绿道", "intensity": "中", "met": "7.0", "duration_min": "25", "target_body_part": "全身", "avoid_injury": "knee,ankle,cardio", "suitable_level": "intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "心肺,减脂"},
    {"name": "原地踏步", "category": "有氧", "preference_type": "居家,综合训练", "location_type": "居家,室内场馆", "intensity": "低", "met": "3.0", "duration_min": "10", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate", "risk_allowed": "low,medium,high", "goal_tags": "低冲击,心肺"},
    {"name": "开合跳", "category": "有氧", "preference_type": "居家,综合训练", "location_type": "居家,健身房", "intensity": "中高", "met": "8.0", "duration_min": "8", "target_body_part": "全身", "avoid_injury": "knee,ankle,back,cardio", "suitable_level": "intermediate,advanced", "risk_allowed": "low", "goal_tags": "燃脂,心肺"},
    {"name": "骑行", "category": "有氧", "preference_type": "骑行,综合训练", "location_type": "绿道,公园,健身房", "intensity": "中", "met": "6.8", "duration_min": "30", "target_body_part": "下肢", "avoid_injury": "knee", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "心肺,低冲击"},
    {"name": "游泳", "category": "有氧", "preference_type": "游泳,综合训练", "location_type": "游泳馆", "intensity": "中", "met": "6.0", "duration_min": "30", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "低冲击,心肺"},
    {"name": "深蹲", "category": "力量", "preference_type": "力量训练,综合训练", "location_type": "居家,健身房,操场", "intensity": "中", "met": "5.0", "duration_min": "10", "target_body_part": "下肢", "avoid_injury": "knee,back", "suitable_level": "intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "力量,下肢"},
    {"name": "臀桥", "category": "力量", "preference_type": "居家,力量训练", "location_type": "居家,健身房", "intensity": "低到中", "met": "3.8", "duration_min": "8", "target_body_part": "臀腿,核心", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium,high", "goal_tags": "核心,下肢,腰背友好"},
    {"name": "俯卧撑", "category": "力量", "preference_type": "力量训练,居家", "location_type": "居家,健身房,操场", "intensity": "中", "met": "3.8", "duration_min": "8", "target_body_part": "胸,肩,手臂", "avoid_injury": "shoulder,wrist", "suitable_level": "intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "上肢,力量"},
    {"name": "跪姿俯卧撑", "category": "力量", "preference_type": "力量训练,居家", "location_type": "居家,健身房", "intensity": "低到中", "met": "3.0", "duration_min": "8", "target_body_part": "胸,肩,手臂", "avoid_injury": "shoulder,wrist", "suitable_level": "beginner,intermediate", "risk_allowed": "low,medium", "goal_tags": "上肢,入门"},
    {"name": "平板支撑", "category": "核心", "preference_type": "核心训练,居家", "location_type": "居家,健身房", "intensity": "中", "met": "3.3", "duration_min": "5", "target_body_part": "核心", "avoid_injury": "back,wrist,shoulder", "suitable_level": "intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "核心,稳定"},
    {"name": "鸟狗式", "category": "核心", "preference_type": "康复训练,居家", "location_type": "居家,健身房", "intensity": "低", "met": "2.8", "duration_min": "6", "target_body_part": "核心,腰背", "avoid_injury": "", "suitable_level": "beginner,intermediate", "risk_allowed": "low,medium,high", "goal_tags": "核心稳定,腰背友好"},
    {"name": "瑜伽拉伸", "category": "拉伸", "preference_type": "瑜伽,拉伸,居家", "location_type": "居家,瑜伽馆,健身房", "intensity": "低", "met": "2.5", "duration_min": "15", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium,high", "goal_tags": "柔韧,恢复"},
    {"name": "肩颈拉伸", "category": "拉伸", "preference_type": "拉伸,办公室训练", "location_type": "居家,室内", "intensity": "低", "met": "2.0", "duration_min": "5", "target_body_part": "肩颈", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium,high", "goal_tags": "恢复,放松"},
    {"name": "弹力带划船", "category": "力量", "preference_type": "力量训练,居家", "location_type": "居家,健身房", "intensity": "低到中", "met": "3.5", "duration_min": "8", "target_body_part": "背部,手臂", "avoid_injury": "shoulder", "suitable_level": "beginner,intermediate", "risk_allowed": "low,medium", "goal_tags": "上肢,姿态"},
    {"name": "椭圆机", "category": "有氧", "preference_type": "健身房,综合训练", "location_type": "健身房", "intensity": "中", "met": "5.0", "duration_min": "25", "target_body_part": "全身", "avoid_injury": "", "suitable_level": "beginner,intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "低冲击,心肺"},
    {"name": "羽毛球", "category": "球类", "preference_type": "球类,综合训练", "location_type": "体育馆,羽毛球馆", "intensity": "中", "met": "5.5", "duration_min": "30", "target_body_part": "全身", "avoid_injury": "knee,ankle,shoulder,cardio", "suitable_level": "intermediate,advanced", "risk_allowed": "low,medium", "goal_tags": "协调,心肺"},
]


def request_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "FitFlowDataCollector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(path: Path, tables: dict[str, tuple[list[dict], list[str]]]) -> None:
    with sqlite3.connect(path) as conn:
        for table_name, (rows, columns) in tables.items():
            quoted_columns = ", ".join(f'"{column}" TEXT' for column in columns)
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.execute(f'CREATE TABLE "{table_name}" ({quoted_columns})')
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                quoted_names = ", ".join(f'"{column}"' for column in columns)
                conn.executemany(
                    f'INSERT INTO "{table_name}" ({quoted_names}) VALUES ({placeholders})',
                    [[row.get(column, "") for column in columns] for row in rows],
                )
        conn.commit()


def request_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "FitFlowDataCollector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def build_body_reference_from_nhanes() -> list[dict]:
    try:
        import pandas as pd
    except ImportError:
        print("pandas is not installed: skip CDC NHANES body reference.", file=sys.stderr)
        return []

    try:
        demo = pd.read_sas(io.BytesIO(request_bytes(NHANES_DEMO_URL)), format="xport")
        bmx = pd.read_sas(io.BytesIO(request_bytes(NHANES_BMX_URL)), format="xport")
    except Exception as exc:
        print(f"CDC NHANES download/read failed: {exc}", file=sys.stderr)
        return []

    needed_demo = ["SEQN", "RIDAGEYR", "RIAGENDR"]
    needed_bmx = ["SEQN", "BMXWT", "BMXHT", "BMXBMI"]
    if any(column not in demo.columns for column in needed_demo) or any(column not in bmx.columns for column in needed_bmx):
        print("CDC NHANES schema changed: skip body reference.", file=sys.stderr)
        return []

    df = demo[needed_demo].merge(bmx[needed_bmx], on="SEQN").dropna()
    df = df[df["RIDAGEYR"] >= 13].copy()
    df["age_group"] = df["RIDAGEYR"].apply(age_group)
    df["gender"] = df["RIAGENDR"].map({1: "male", 2: "female"}).fillna("unknown")
    df["bmi_category_china"] = df["BMXBMI"].apply(bmi_category_china)

    rows = []
    grouped = df.groupby(["age_group", "gender", "bmi_category_china"], dropna=False)
    for (age_group_name, gender, bmi_category), group in grouped:
        if len(group) < 5:
            continue
        rows.append({
            "source": "CDC NHANES 2017-2020 pre-pandemic",
            "age_group": age_group_name,
            "gender": gender,
            "bmi_category_china": bmi_category,
            "sample_count": str(int(len(group))),
            "height_cm_p50": f"{group['BMXHT'].median():.1f}",
            "weight_kg_p50": f"{group['BMXWT'].median():.1f}",
            "bmi_p25": f"{group['BMXBMI'].quantile(0.25):.1f}",
            "bmi_p50": f"{group['BMXBMI'].median():.1f}",
            "bmi_p75": f"{group['BMXBMI'].quantile(0.75):.1f}",
        })
    return rows


def age_group(age: float) -> str:
    bins = [(13, 17), (18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 120)]
    for low, high in bins:
        if low <= age <= high:
            return f"{low}-{high}"
    return "other"


def bmi_category_china(bmi: float) -> str:
    if bmi < 18.5:
        return "偏瘦"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "超重"
    return "肥胖"


def fetch_activity_met_reference() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for url in COMPENDIUM_URLS:
        try:
            html = request_bytes(url, timeout=40).decode("utf-8", errors="ignore")
        except Exception as exc:
            print(f"Adult Compendium fetch failed for {url}: {exc}", file=sys.stderr)
            continue

        text = re.sub(r"<[^>]+>", "\n", html)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        category = url.rstrip("/").split("/")[-1]

        for line in text.splitlines():
            item = " ".join(line.split())
            match = re.match(r"^(\d{5})\s+(\d+(?:\.\d+)?)\s+(.{8,})$", item)
            if not match:
                continue
            activity_code, met, activity_name = match.groups()
            if activity_code in seen:
                continue
            seen.add(activity_code)
            rows.append({
                "source": "Adult Compendium of Physical Activities",
                "category": category,
                "activity_code": activity_code,
                "met": met,
                "activity_name": activity_name[:240],
                "intensity": met_to_intensity(float(met)),
            })

    if not rows:
        rows = fallback_met_rows()
    return rows


def met_to_intensity(met: float) -> str:
    if met < 3:
        return "低"
    if met < 6:
        return "中"
    return "高"


def fallback_met_rows() -> list[dict]:
    return [
        {
            "source": "Fallback seed from exercise_library_seed",
            "category": item["category"],
            "activity_code": f"seed_{index:03d}",
            "met": item["met"],
            "activity_name": item["name"],
            "intensity": met_to_intensity(float(item["met"])),
        }
        for index, item in enumerate(EXERCISE_LIBRARY_SEED, start=1)
    ]


def amap_place_search(amap_key: str, city: str, pages: int, offset: int, sleep_sec: float) -> list[dict]:
    if not amap_key:
        print("AMAP_KEY is empty: skip Shijiazhuang POI collection.", file=sys.stderr)
        return []

    rows: list[dict] = []
    seen: set[str] = set()

    for group, keywords in POI_KEYWORDS.items():
        for keyword in keywords:
            for page in range(1, pages + 1):
                params = {
                    "key": amap_key,
                    "keywords": keyword,
                    "city": city,
                    "citylimit": "true",
                    "offset": str(offset),
                    "page": str(page),
                    "extensions": "all",
                    "output": "json",
                }
                url = "https://restapi.amap.com/v3/place/text?" + urllib.parse.urlencode(params)
                data = request_json(url)
                if data.get("status") != "1":
                    message = data.get("info") or data.get("infocode") or "unknown AMap error"
                    print(f"AMap failed for {keyword} page {page}: {message}", file=sys.stderr)
                    break

                pois = data.get("pois") or []
                if not pois:
                    break

                for poi in pois:
                    location = poi.get("location", "")
                    unique_key = poi.get("id") or f"{poi.get('name')}|{location}"
                    if unique_key in seen:
                        continue
                    seen.add(unique_key)

                    biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
                    longitude, latitude = split_location(location)
                    rows.append({
                        "source": "amap",
                        "city": city,
                        "keyword": keyword,
                        "venue_group": group,
                        "poi_id": poi.get("id", ""),
                        "name": poi.get("name", ""),
                        "type": poi.get("type", ""),
                        "typecode": poi.get("typecode", ""),
                        "address": poi.get("address", ""),
                        "district": poi.get("adname", ""),
                        "longitude": longitude,
                        "latitude": latitude,
                        "tel": poi.get("tel", ""),
                        "rating": biz_ext.get("rating", ""),
                        "cost": biz_ext.get("cost", ""),
                        "suitable_sports": infer_suitable_sports(group, keyword, poi.get("name", "")),
                    })

                time.sleep(sleep_sec)

    return rows


def split_location(location: str) -> tuple[str, str]:
    if not location or "," not in location:
        return "", ""
    longitude, latitude = location.split(",", 1)
    return longitude.strip(), latitude.strip()


def infer_suitable_sports(group: str, keyword: str, name: str) -> str:
    text = f"{keyword} {name}"
    if group == "outdoor":
        return "快走,慢跑,骑行,拉伸,低强度有氧"
    if "游泳" in text:
        return "游泳,低冲击有氧"
    if "瑜伽" in text or "普拉提" in text:
        return "瑜伽,普拉提,柔韧训练,核心稳定"
    if "篮球" in text:
        return "篮球,敏捷训练,团队运动"
    if "羽毛球" in text or "乒乓球" in text:
        return "挥拍运动,协调训练,中等强度有氧"
    if group == "gym":
        return "力量训练,有氧器械,核心训练,拉伸"
    return "综合训练,有氧训练,力量训练"


def fetch_weather(latitude: float, longitude: float) -> tuple[dict, list[dict]]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m",
        "timezone": "Asia/Shanghai",
        "forecast_days": 3,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    data = request_json(url)
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    hourly_rows = build_hourly_rows(hourly, prefix="weather")
    return current, hourly_rows


def fetch_air_quality(latitude: float, longitude: float) -> tuple[dict, list[dict]]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
        "hourly": "pm10,pm2_5,us_aqi",
        "timezone": "Asia/Shanghai",
        "forecast_days": 3,
    }
    url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode(params)
    data = request_json(url)
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    hourly_rows = build_hourly_rows(hourly, prefix="air")
    return current, hourly_rows


def build_hourly_rows(hourly: dict, prefix: str) -> list[dict]:
    times = hourly.get("time") or []
    rows = []
    for index, item_time in enumerate(times):
        row = {"time": item_time, "source_type": prefix}
        for key, values in hourly.items():
            if key == "time":
                continue
            row[key] = values[index] if index < len(values) else ""
        rows.append(row)
    return rows


def current_to_rows(city: str, current: dict, source: str) -> list[dict]:
    return [
        {
            "city": city,
            "source": source,
            "metric": key,
            "value": value,
            "captured_at": current.get("time", ""),
        }
        for key, value in current.items()
        if key != "time"
    ]


def build_environment_summary(city: str, weather: dict, air: dict) -> list[dict]:
    us_aqi = safe_float(air.get("us_aqi"))
    pm25 = safe_float(air.get("pm2_5"))
    precipitation = safe_float(weather.get("precipitation"))
    wind_speed = safe_float(weather.get("wind_speed_10m"))

    if us_aqi is not None and us_aqi > 100 or pm25 is not None and pm25 > 35:
        level = "poor_air"
        advice = "空气质量偏差，优先推荐室内训练，减少长时间户外有氧。"
    elif precipitation is not None and precipitation > 0 or wind_speed is not None and wind_speed >= 28:
        level = "rain_or_wind"
        advice = "天气不稳定，优先推荐室内体感训练、力量训练和拉伸。"
    elif us_aqi is not None and us_aqi <= 50:
        level = "good_outdoor"
        advice = "适合室外训练，可推荐公园、操场、绿道等场景。"
    else:
        level = "moderate_air"
        advice = "适合低到中等强度训练，敏感人群控制室外时长。"

    return [{
        "city": city,
        "environment_level": level,
        "advice": advice,
        "temperature_2m": weather.get("temperature_2m", ""),
        "relative_humidity_2m": weather.get("relative_humidity_2m", ""),
        "precipitation": weather.get("precipitation", ""),
        "wind_speed_10m": weather.get("wind_speed_10m", ""),
        "pm2_5": air.get("pm2_5", ""),
        "pm10": air.get("pm10", ""),
        "us_aqi": air.get("us_aqi", ""),
        "captured_at": weather.get("time", "") or air.get("time", ""),
    }]


def safe_float(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Shijiazhuang fitness reference data.")
    parser.add_argument("--amap-key", default=os.getenv("AMAP_KEY", ""), help="AMap Web Service key.")
    parser.add_argument("--city", default=SHIJIAZHUANG_CENTER["city"])
    parser.add_argument("--latitude", type=float, default=SHIJIAZHUANG_CENTER["latitude"])
    parser.add_argument("--longitude", type=float, default=SHIJIAZHUANG_CENTER["longitude"])
    parser.add_argument("--pages", type=int, default=3, help="AMap pages per keyword.")
    parser.add_argument("--offset", type=int, default=20, help="AMap page size, max is usually 25.")
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between AMap requests.")
    parser.add_argument("--out-dir", default="data_seed/shijiazhuang")
    parser.add_argument("--skip-nhanes", action="store_true", help="Skip CDC NHANES body reference.")
    parser.add_argument("--skip-met", action="store_true", help="Skip Adult Compendium MET reference.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    venues = amap_place_search(args.amap_key, args.city, args.pages, args.offset, args.sleep)
    weather_current, weather_hourly = fetch_weather(args.latitude, args.longitude)
    air_current, air_hourly = fetch_air_quality(args.latitude, args.longitude)
    weather_rows = current_to_rows(args.city, weather_current, "open_meteo_forecast")
    air_rows = current_to_rows(args.city, air_current, "open_meteo_air_quality")
    summary_rows = build_environment_summary(args.city, weather_current, air_current)
    body_reference = [] if args.skip_nhanes else build_body_reference_from_nhanes()
    activity_met_reference = [] if args.skip_met else fetch_activity_met_reference()

    venue_columns = [
        "source", "city", "keyword", "venue_group", "poi_id", "name", "type", "typecode",
        "address", "district", "longitude", "latitude", "tel", "rating", "cost",
        "suitable_sports",
    ]
    metric_columns = ["city", "source", "metric", "value", "captured_at"]
    hourly_columns = sorted(set().union(*(row.keys() for row in weather_hourly + air_hourly))) if weather_hourly or air_hourly else ["time", "source_type"]
    rule_columns = ["rule_code", "condition", "recommendation", "suitable_location", "avoid_tags"]
    bmi_rule_columns = ["standard", "category", "min_bmi", "max_bmi", "risk_hint"]
    duration_rule_columns = ["population", "risk_level", "weekly_minutes", "strength_days", "single_session_minutes", "intensity", "source"]
    injury_rule_columns = ["injury_code", "injury_name", "avoid_tags", "safe_tags", "note"]
    exercise_columns = [
        "name", "category", "preference_type", "location_type", "intensity", "met",
        "duration_min", "target_body_part", "avoid_injury", "suitable_level",
        "risk_allowed", "goal_tags",
    ]
    body_columns = [
        "source", "age_group", "gender", "bmi_category_china", "sample_count",
        "height_cm_p50", "weight_kg_p50", "bmi_p25", "bmi_p50", "bmi_p75",
    ]
    met_columns = ["source", "category", "activity_code", "met", "activity_name", "intensity"]
    summary_columns = [
        "city", "environment_level", "advice", "temperature_2m", "relative_humidity_2m",
        "precipitation", "wind_speed_10m", "pm2_5", "pm10", "us_aqi", "captured_at",
    ]

    write_csv(out_dir / "shijiazhuang_venues.csv", venues, venue_columns)
    write_csv(out_dir / "shijiazhuang_weather_current.csv", weather_rows, metric_columns)
    write_csv(out_dir / "shijiazhuang_air_quality_current.csv", air_rows, metric_columns)
    write_csv(out_dir / "shijiazhuang_environment_hourly.csv", weather_hourly + air_hourly, hourly_columns)
    write_csv(out_dir / "shijiazhuang_environment_summary.csv", summary_rows, summary_columns)
    write_csv(out_dir / "training_environment_rules.csv", TRAINING_ENVIRONMENT_RULES, rule_columns)
    write_csv(out_dir / "bmi_rules.csv", BMI_RULES, bmi_rule_columns)
    write_csv(out_dir / "training_duration_rules.csv", TRAINING_DURATION_RULES, duration_rule_columns)
    write_csv(out_dir / "injury_avoidance_rules.csv", INJURY_AVOIDANCE_RULES, injury_rule_columns)
    write_csv(out_dir / "exercise_library_seed.csv", EXERCISE_LIBRARY_SEED, exercise_columns)
    write_csv(out_dir / "body_reference_nhanes.csv", body_reference, body_columns)
    write_csv(out_dir / "activity_met_reference.csv", activity_met_reference, met_columns)

    write_sqlite(
        out_dir / "shijiazhuang_fitness_reference.db",
        {
            "shijiazhuang_venues": (venues, venue_columns),
            "weather_current": (weather_rows, metric_columns),
            "air_quality_current": (air_rows, metric_columns),
            "environment_hourly": (weather_hourly + air_hourly, hourly_columns),
            "environment_summary": (summary_rows, summary_columns),
            "training_environment_rules": (TRAINING_ENVIRONMENT_RULES, rule_columns),
            "bmi_rules": (BMI_RULES, bmi_rule_columns),
            "training_duration_rules": (TRAINING_DURATION_RULES, duration_rule_columns),
            "injury_avoidance_rules": (INJURY_AVOIDANCE_RULES, injury_rule_columns),
            "exercise_library_seed": (EXERCISE_LIBRARY_SEED, exercise_columns),
            "body_reference_nhanes": (body_reference, body_columns),
            "activity_met_reference": (activity_met_reference, met_columns),
        },
    )

    manifest = {
        "city": args.city,
        "latitude": args.latitude,
        "longitude": args.longitude,
        "venue_count": len(venues),
        "weather_metric_count": len(weather_rows),
        "air_metric_count": len(air_rows),
        "hourly_count": len(weather_hourly) + len(air_hourly),
        "body_reference_count": len(body_reference),
        "activity_met_count": len(activity_met_reference),
        "bmi_rule_count": len(BMI_RULES),
        "duration_rule_count": len(TRAINING_DURATION_RULES),
        "injury_rule_count": len(INJURY_AVOIDANCE_RULES),
        "exercise_seed_count": len(EXERCISE_LIBRARY_SEED),
        "output_dir": str(out_dir),
        "note": "AMap venue data requires AMAP_KEY. NHANES requires pandas. Weather and air quality use Open-Meteo.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
