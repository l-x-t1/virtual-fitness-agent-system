from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation import AgentRegressionRunner, load_cases
from app.evaluation.judge import LLMAsJudge, ManualReviewStore, ReviewRecord
from app.llm import LLMClient


DEFAULT_CASES = ROOT / "tools" / "data_seed" / "agent_eval_cases.json"
DEFAULT_REPORT = ROOT / ".agent_eval" / "latest_report.json"
DEFAULT_REVIEW = ROOT / ".agent_eval" / "manual_reviews.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run agent regression evaluation.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Path to evaluation cases JSON.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to write the JSON report.")
    parser.add_argument("--baseline", help="Optional baseline report path for comparison.")
    parser.add_argument("--provider", help="LLM provider for evaluated agents.")
    parser.add_argument("--model", help="LLM model for evaluated agents.")
    parser.add_argument("--judge-provider", help="LLM provider used for LLM-as-judge.")
    parser.add_argument("--judge-model", help="LLM model used for LLM-as-judge.")
    parser.add_argument("--review-file", default=str(DEFAULT_REVIEW), help="Human review JSONL store.")
    parser.add_argument("--min-overall", type=float, default=0.62, help="Pass threshold for overall score.")
    parser.add_argument("--min-relevance", type=float, default=0.55, help="Pass threshold for answer relevance.")
    parser.add_argument("--min-citation-hit", type=float, default=0.5, help="Pass threshold for citation hit rate.")
    parser.add_argument("--enforce", action="store_true", help="Exit non-zero when thresholds are not met.")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="Run the full regression suite.")
    run.set_defaults(command="run")
    compare = sub.add_parser("compare", help="Compare two regression reports.")
    compare.add_argument("--current", default=str(DEFAULT_REPORT), help="Current report path.")
    compare.add_argument("--baseline", required=True, help="Baseline report path.")
    compare.set_defaults(command="compare")
    review = sub.add_parser("review", help="Append a human review decision for a case.")
    review.add_argument("--case-id", required=True)
    review.add_argument("--decision", required=True, choices=["pass", "fail", "needs_follow_up"])
    review.add_argument("--notes", default="")
    review.add_argument("--reviewer", default="human")
    review.add_argument("--review-file", default=str(DEFAULT_REVIEW))
    review.set_defaults(command="review")
    pending = sub.add_parser("pending", help="List cases still needing human review.")
    pending.add_argument("--report", default=str(DEFAULT_REPORT))
    pending.add_argument("--review-file", default=str(DEFAULT_REVIEW))
    pending.set_defaults(command="pending")
    return parser


def make_llm(provider: str | None, model: str | None) -> LLMClient:
    if provider or model:
        return LLMClient(provider=provider, model=model)
    return LLMClient()


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_report(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    metrics = ("citation_hit_rate", "answer_relevance", "safety_score", "overall_score", "degradation_count")
    compare: dict[str, Any] = {}
    for key in metrics:
        current_value = float(current.get(key) or 0)
        baseline_value = float(baseline.get(key) or 0)
        compare[key] = {
            "current": round(current_value, 4),
            "baseline": round(baseline_value, 4),
            "delta": round(current_value - baseline_value, 4),
        }
    return compare


def run_regression(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_cases(args.cases)
    agent_llm = make_llm(args.provider, args.model)
    judge_llm = make_llm(args.judge_provider or args.provider, args.judge_model or args.model)
    judge = LLMAsJudge(judge_llm, pass_threshold=args.min_overall, review_threshold=max(0.45, args.min_overall - 0.18))
    runner = AgentRegressionRunner(cases, llm_client=agent_llm, judge=judge)
    report = runner.run()
    payload = report.to_dict()
    baseline_path = args.baseline
    if baseline_path and Path(baseline_path).exists():
        payload["baseline_compare"] = compare_reports(payload, load_report(baseline_path))
    save_report(args.report, payload)
    return payload


def print_report(payload: dict[str, Any], *, json_only: bool) -> None:
    if json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Cases: {payload['case_count']}")
    print(f"Pass/Review/Fail: {payload['pass_count']}/{payload['review_count']}/{payload['fail_count']}")
    print(f"Answer relevance: {payload['answer_relevance']:.3f}")
    print(f"Citation hit rate: {payload['citation_hit_rate']:.3f}")
    print(f"Safety score: {payload['safety_score']:.3f}")
    print(f"Overall score: {payload['overall_score']:.3f}")
    print(f"Degradation count: {payload['degradation_count']}")
    print(f"Avg latency(ms): {payload['average_latency_ms']:.1f}")
    if payload.get("manual_review_cases"):
        print("Manual review:", ", ".join(payload["manual_review_cases"]))
    compare = payload.get("baseline_compare") or {}
    if compare:
        print("Baseline compare:")
        for key, item in compare.items():
            print(f"  {key}: current={item['current']:.3f} baseline={item['baseline']:.3f} delta={item['delta']:+.3f}")


def enforce(payload: dict[str, Any], args: argparse.Namespace) -> int:
    if payload["overall_score"] < args.min_overall:
        return 1
    if payload["answer_relevance"] < args.min_relevance:
        return 1
    if payload["citation_hit_rate"] < args.min_citation_hit:
        return 1
    if payload["fail_count"] > 0:
        return 1
    return 0


def add_review(args: argparse.Namespace) -> int:
    store = ManualReviewStore(args.review_file)
    store.append(
        ReviewRecord(
            case_id=args.case_id,
            reviewer=args.reviewer,
            decision=args.decision,
            notes=args.notes,
        )
    )
    print(f"Saved review for {args.case_id} -> {args.decision}")
    return 0


def list_pending(args: argparse.Namespace) -> int:
    payload = load_report(args.report)
    reviewed = ManualReviewStore(args.review_file).reviewed_case_ids()
    pending = [case_id for case_id in payload.get("manual_review_cases") or [] if case_id not in reviewed]
    if not pending:
        print("No pending manual review items.")
        return 0
    for case_id in pending:
        print(case_id)
    return 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "run"
    if command == "review":
        return add_review(args)
    if command == "pending":
        return list_pending(args)
    if command == "compare":
        current = load_report(args.current)
        baseline = load_report(args.baseline)
        payload = {
            "current": current,
            "baseline": baseline,
            "compare": compare_reports(current, baseline),
        }
        print_report(
            {
                "case_count": current.get("case_count", 0),
                "pass_count": current.get("pass_count", 0),
                "review_count": current.get("review_count", 0),
                "fail_count": current.get("fail_count", 0),
                "answer_relevance": current.get("answer_relevance", 0),
                "citation_hit_rate": current.get("citation_hit_rate", 0),
                "safety_score": current.get("safety_score", 0),
                "overall_score": current.get("overall_score", 0),
                "degradation_count": current.get("degradation_count", 0),
                "average_latency_ms": current.get("average_latency_ms", 0),
                "manual_review_cases": current.get("manual_review_cases", []),
                "baseline_compare": payload["compare"],
            },
            json_only=args.json,
        )
        return 0
    payload = run_regression(args)
    print_report(payload, json_only=args.json)
    return enforce(payload, args) if args.enforce else 0


if __name__ == "__main__":
    raise SystemExit(main())
