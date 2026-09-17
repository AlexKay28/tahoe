# final_test.py provenance

Copied VERBATIM from the corp Harbor adapter template:
`ml/zeliboba/alignment/tool_calling/harbor_bench/src/adapters/livecodebench/template/final_test.py`
(Arcadia, trunk, 2026-09-17). The template itself derives from the upstream
LiveCodeBench evaluation script (github.com/LiveCodeBench/LiveCodeBench, MIT).
The corp team parity-tested this verifier against model runs
(`parity_experiment.json` in the same adapter directory).

Used unmodified by `benchmarks/lcb_sandbox.py` (issue #99): single-turn model
answer -> solution.py -> verifier subprocess (network-isolated, hard timeout).
