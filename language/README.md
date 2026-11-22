# The TAHOE Language

TAHOE is a structured reasoning language: a notation of typed epistemic
references, named reasoning protocols, and economy rules that form a
logic-level pseudocode for how a model should think.

This directory holds the language as **delivered artifacts** — everything an
experiment or a deployment needs to give a model the language.

## Layout

```
language/
├── skills/                  # thinking skills (system prompts) — the deliverable
│   ├── tahoe-93.txt         # canonical skill (93 tokens) — used in all headline results
│   ├── triz-implicit.txt    # variant: adds ideal-first search bounding (83 words)
│   └── variants/            # ablation artifacts (kept as evidence)
│       ├── tahoe-50/150/200.txt   # size ablation
│       ├── triz-implicit-50/150.txt
│       └── triz-explicit.txt      # the FAILED explicit-notation variant (kept deliberately)
└── baselines/               # baseline prompts for arm comparisons
    ├── cot.txt  cod.txt  tot.txt  react.txt
```

## Design hypothesis and output-contract confound

TAHOE is designed to shape reasoning without exposing its notation in the
visible answer. The canonical skill nevertheless explicitly constrains that
answer: its final sentence says `Output only the answer.` Archived prompt
results therefore measure the **structure + answer-only bundle**; they do not
show that the model internally used typed commitments or isolate structure
from forced brevity. The controlled factorial that separates these components
is prepared but has not been run (`docs/PREREGISTRATION-structure-answer.md`).

The explicit-notation variant measurably decreased quality and increased
tokens (see `insights/compact-language.md`; its negative artifact is kept in
`skills/variants/triz-explicit.txt`). That is evidence against that particular
visible-notation contract, not a general law against every output contract.

## Skill-size ablation

Stored-grade results were similar across the tested 33–162-word skills. This
size ablation does not identify the active mechanism: structure, shared output
contracts, and generic brevity remain confounded. The canonical skill is 93
tokens.

## Contract with the runtime

The skill prompt teaches the language; the runtime (`src/tahoe/`) provides the
reference grammar, parser, type-checker, and coordinator. At inference time
only the prompt is needed; the runtime validates, executes deterministically
where possible, and (optionally, `vm_mode/`) executes programs step-by-step.
