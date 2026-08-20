# Agent Evaluation

## Goal

Build a repeatable evaluation loop for prompt changes and agent behavior.

## What this repo now provides

- Golden cases in `tools/data_seed/agent_eval_cases.json`
- LLM-as-judge scoring for:
  - answer relevance
  - citation hit rate
  - safety
- Manual review queue in `.agent_eval/manual_reviews.jsonl`
- One-click regression runner:

```bash
python tools/run_agent_regression.py run
```

- Baseline comparison:

```bash
python tools/run_agent_regression.py compare --baseline path/to/baseline.json
```

## Metrics

- `citation_hit_rate`: expected citation keywords found in the answer or evidence
- `answer_relevance`: semantic overlap between expected and actual answers
- `degradation_count`: runs that fell back to demo/fallback or failed judge checks

## Manual review

Cases whose judge confidence is low or whose score is below threshold are exported into the manual review queue.

Append a human decision:

```bash
python tools/run_agent_regression.py review --case-id chat_knee_low_impact --decision pass --notes "answer is safe"
```

List unresolved items:

```bash
python tools/run_agent_regression.py pending
```

## Git hook

The repo includes `.githooks/pre-commit`.

One-time setup:

```bash
git config core.hooksPath .githooks
```

After this, staged changes touching prompts, agent code, or evaluation code will trigger regression before commit.

## Open-source compatibility

The case format is intentionally JSON-first so it can be adapted to:

- promptfoo
- DeepEval
- Ragas
- LangSmith

Recommended mapping:

- `question` -> promptfoo test input / DeepEval input
- `expected_answer` -> target response / rubric reference
- `expected_citations` -> citation accuracy check
- `judge` JSON -> evaluation output artifact

This keeps the repo portable even if the team later swaps the judge implementation.
