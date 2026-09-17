# DeepSWE — runbook for the docker-capable VM (issue #100)

Two arms, identical scaffold (Pier + mini-swe-agent + same step budget):
**A. default policy** (stock mini-swe-agent prompt) vs **B. tahoe-policy**
(tahoe-93 skill as the agent system template). Model for BOTH:
`GLM-5.3-Flash_alexkay28/.` via Eliza. Sanity gate before the A/B.

## 0. VM prerequisites

- Docker daemon running (`docker info` OK), ≥150GB free disk, ≥8 CPU, 32GB RAM
- Python 3.12 (`apt install python3.12` or uv)

## 1. Harness + data

```bash
python3.12 -m venv ~/pier-venv && source ~/pier-venv/bin/activate
# corp mirror lacks the package; use public PyPI
pip install --index-url https://pypi.org/simple/ datacurve-pier   # 0.3.1
pier --version                                                     # 0.3.1

git clone --depth 1 https://github.com/datacurve-ai/deep-swe ~/deep-swe
ls ~/deep-swe/tasks/*/task.toml | wc -l                            # 113
```

## 2. Endpoint env (both arms)

```bash
export OPENAI_BASE_URL="https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1"
export OPENAI_API_KEY="$(cat ~/.soy/token)"
export SSL_CERT_FILE=/etc/ssl/certs/yandex-ca.pem
```

Model name for Pier/litellm: `openai/GLM-5.3-Flash_alexkay28`.
The egress-proxy allowlist is derived from `OPENAI_BASE_URL` automatically
(Pier collects provider domains from agent config).

## 3. Sanity gate (MUST pass before the A/B)

~15 tasks, default arm; result must be statistically compatible with the
published `glm-5.3-flash[max]` = 63%±4 pass@1. If it lands far below, fix
harness drift first (model config, effort level, image versions) — do NOT
start the A/B on a drifted harness.

```bash
cd ~/deep-swe
pier run tasks/ \
  --agent mini-swe-agent \
  --model openai/GLM-5.3-Flash_alexkay28 \
  --env docker \
  --n-tasks 15 --sample-seed 0 \
  --output-dir ~/deepswe-runs/sanity
# pass@1 across 15 tasks: expect roughly 50-75% band; record exact number + steps + tokens
```

## 4. Arm A — default policy (113 tasks, 1 rollout/task first pass)

```bash
pier run tasks/ \
  --agent mini-swe-agent \
  --model openai/GLM-5.3-Flash_alexkay28 \
  --env docker \
  --output-dir ~/deepswe-runs/armA-default
```

## 5. Arm B — tahoe policy

Pier's `MiniSweAgent` accepts `config_file` (upstream mini-swe-agent yaml,
which owns the system template). The JobConfig `agents[].kwargs` passes it
through — no code fork. The tahoe config = default mini-swe-agent config with
`system_template` replaced by the tahoe-93 skill text; ONLY the system prompt
differs between arms.

```bash
# ~/tahoe-job.yaml
# agents:
#   - name: mini-swe-agent
#     model_name: openai/GLM-5.3-Flash_alexkay28
#     kwargs:
#       config_file: /home/<user>/tahoe-mini-config.yaml
#
# tahoe-mini-config.yaml: copy the default mini-swe-agent config
# (from the mini-swe-agent package / Pier's defaults), then set:
#   system_template: |
#     <contents of language/skills/tahoe-93.txt from the tahoe repo>

pier run --config ~/tahoe-job.yaml tasks/ \
  --env docker \
  --output-dir ~/deepswe-runs/armB-tahoe
```

## 6. Collect

Per trial artifacts: `reward.json` (binary reward + f2p/p2p fractions),
`ctrf.json`, `run.log`, ATIF trajectory with `llm_call_count`,
`peak_context_tokens`. Aggregate: pass@1 (macro over tasks), steps, output
tokens, cost per task; per-arm comparison table →
`benchmarks/results/2026-09-16-deepswe/` in the tahoe repo.

## Notes

- Trials are independent; parallelize with Pier's concurrency option up to
  machine limits (each trial: 2 CPU / 8GB RAM / 20GB disk).
- Verifier image builds locally per trial (thin layer over the prebuilt image)
  — needs network for its own base pull once.
- `reward.txt == -1` is the infra-failure sentinel; exclude from pass@1 and
  count separately (infra vs model failures).
- v1.1 task set = the GitHub repo trunk; Pier must be > 0.3.0.
