# Open Forge P1 — Documents Index

Central documentation for the Open Forge datasheet parser (Problem 1).

## Start here

| Document | Purpose |
|---|---|
| [objectives.md](objectives.md) | Six formal problem statements |
| [architecture/PROJECT_CONTEXT.md](architecture/PROJECT_CONTEXT.md) | **Living project status** — phase dashboard, update on every milestone |
| [assessments/p1_assessment_filled.md](assessments/p1_assessment_filled.md) | **Authoritative spec** — schema, models, metrics, phased plan |

## Directory layout

```
documents/
├── README.md                          ← this index
├── objectives.md                      ← problem statements (P1–P6)
├── assessments/
│   ├── p1_assessment.md               ← template (superseded by _filled)
│   └── p1_assessment_filled.md        ← authoritative P1 assessment
├── architecture/
│   ├── PROJECT_CONTEXT.md             ← current status & phase detail
│   └── problem_1_solution.md          ← 4-phase pipeline architecture
├── guides/
│   ├── PROJECT_BOOTSTRAP_GUIDE.md     ← scaffolding & setup templates
│   ├── CODING_STANDARDS_P1.md         ← code style, TDD, config patterns
│   └── QUICK_REFERENCE_PATTERNS.md    ← good/bad patterns cheat sheet
└── phase1/
    ├── CURSOR_PROMPT_PHASE1.md        ← Phase 1 DLA implementation prompt
    └── PHASE1_CORPUS_EVAL_TUNING_LOG.md  ← golden corpus eval tuning history
```

## Reading order (implementers)

1. [assessments/p1_assessment_filled.md](assessments/p1_assessment_filled.md) — requirements and exit metrics
2. [architecture/PROJECT_CONTEXT.md](architecture/PROJECT_CONTEXT.md) — what is done vs pending
3. [guides/CODING_STANDARDS_P1.md](guides/CODING_STANDARDS_P1.md) — how to write code
4. [guides/QUICK_REFERENCE_PATTERNS.md](guides/QUICK_REFERENCE_PATTERNS.md) — patterns to follow/avoid
5. [architecture/problem_1_solution.md](architecture/problem_1_solution.md) — architecture narrative
6. [phase1/CURSOR_PROMPT_PHASE1.md](phase1/CURSOR_PROMPT_PHASE1.md) — Phase 1 module specs

## Phase 1 eval

- Live results: [`../p1-parser/eval/phase1/PHASE1_RESULTS.md`](../p1-parser/eval/phase1/PHASE1_RESULTS.md)
- Tuning methodology: [phase1/PHASE1_CORPUS_EVAL_TUNING_LOG.md](phase1/PHASE1_CORPUS_EVAL_TUNING_LOG.md)
