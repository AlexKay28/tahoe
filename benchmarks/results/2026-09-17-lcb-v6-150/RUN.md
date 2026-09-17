# LiveCodeBench release_v6-150 — tahoe-93 vs classic (issue #99)

Run date: 2026-09-17 · Model: GLM-5.3-Flash_alexkay28/. · 300 trials (150 × 2 arms × 1 seed), 0 timeouts, 0 verifier errors

## Result

| Arm | Pass@1 (95% CI) | Avg tokens |
|---|---|---|
| classic | 28.7% ± 7.2 (43/150) | 2192 |
| tahoe-93 | 33.3% ± 7.5 (50/150) | 2182 |

Delta **+4.7pp, z=0.87 — not significant** (p≈0.38). Token ratio 0.995×.
All 207 failures are genuine wrong answers — no timeouts, no verifier errors
(sandbox + verifier infra fully clean).

## Interpretation (predeclared-bar discipline)

Single-turn code generation trends positive but does not clear the
significance bar at n=150. H2's caution (code is where overhead hurts) is
NOT confirmed — tahoe is quality-neutral-to-positive at neutral tokens.
Recorded as **null-trending-positive**. Slate picture after four harder
benchmarks: only MMLU-Pro (+4.2pp, z=2.03) is significant; AIME (+6.2),
LCB (+4.7), GPQA (+1.5) trend positive without clearing the bar — direction
consistency across 4/4 benchmarks is itself evidence, but each individually
needs more trials for a verdict-grade claim.

## Sandbox (phase 1, no docker)

- Verifier: corp Harbor adapter template's `final_test.py` copied VERBATIM
  (`benchmarks/verifiers/lcb/`, provenance in that dir) — the corp team
  parity-tested it
- Executor: `benchmarks/lcb_sandbox.py` — per-trial scratch dir
  (config.json + solution.py), subprocess under `sudo unshare -n`
  (network-isolated, root CAP_SYS_ADMIN) + `timeout -k 300`
- Code extraction arm-agnostic: last ```python fenced block, else whole answer
- Validated: known-good solution → PASS; known-bad → FAIL (33 private+public
  tests each)

## Data

- `benchmarks/data/lcb_v6_150.jsonl` — the 150 NEWEST problems of
  release_v6 (Jan 18 – Apr 6 2025; 36 easy / 46 medium / 68 hard), by
  `contest_date` desc; + `build_lcb_v6_150.py`
- Contamination caveat: window predates GLM-5.3's likely cutoff — affects
  both arms equally; the delta remains internally valid
- Raw trials: `public_benchmarks.json` (this directory)

## Env + commands

```bash
export TAHOE_API_BASE="https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1"
export TAHOE_API_KEY="$(cat ~/.soy/token)"; export TAHOE_MODEL="."
export SSL_CERT_FILE=/etc/ssl/certs/yandex-ca.pem

python3 benchmarks/data/build_lcb_v6_150.py
BENCHES=lcb BENCH_TRIALS=1 PYTHONPATH=src python3 benchmarks/run_public_bench.py
```
