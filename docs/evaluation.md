# Recorded synthetic regression

Run: `inference-20261009T215459Z`, October 9, 2026 UTC. Ollama 0.33.3, local `qwen3:4b` triage and `qwen3:8b` review. Source, prompts, rules and data were frozen before development evaluation and checked again before and after the test recording. The original synthetic dataset has been used before; this is a repeated regression measurement, not a pristine unseen study.

There are 80 trajectories in five harmful/benign pairs per family, across eight families. The fixed paired manifest assigns 48 trajectories to development and 32 to test. Multiple actions produce 96 development actions (24 harmful, 72 benign) and 64 test actions (16 harmful, 48 benign). Metrics below classify actions, not whole trajectories.

The operating threshold targets at most 5% false alarms on development actions and is applied unchanged to test. Small counts mean this target is coarse and need not hold on test. Live incident/notification thresholds remain 5/8.

| Scorer | Development threshold | Test TP / FN / FP / TN | Recall | False alarms | Precision | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| Rules | 5 | 9 / 7 / 1 / 47 | 56.25% | 2.08% | 90.0% | 64/64 |
| Standalone Qwen3 8B | No feasible threshold; alert-none operating point | 0 / 16 / 0 / 48 | 0% | 0% | Undefined: no alerts | 64/64 |
| Maximum of rules and standalone judge | No feasible threshold; alert-none operating point | 0 / 16 / 0 / 48 | 0% | 0% | Undefined: no alerts | 64/64 |
| Actual live cascade | 5 | 16 / 0 / 3 / 45 | 100% | 6.25% | 84.21% | 64/64 |

The standalone judge had high-scoring benign development cases; no score threshold met the 5% false-alarm target while producing alerts. Its alert-none point misses every harmful test action. This calibration failure is retained in the result, and the standalone judge is not the live routing policy. AUC (0.936 for the standalone judge and 0.978 for the cascade) measures ranking; it does not rescue the failed operating point.

The cascade missed one development dependency-change action and flagged two benign development actions. On test, its three benign alerts occurred in credential-transmission (two) and remote-code-execution (one) families. Each family has only two harmful and six benign test actions. Category counts and both 1% and 5% development-selected operating points are in the full result.

The recording used 160 standalone model requests and 110 cascade stage requests across development and test, with zero retries, failed stages or incomplete actions. Shared model results were cached during repeated metric calculations; requests are not added again for each threshold calculation. The cascade's median test action scoring latency was 0.203ms because many actions settled through rules; this is not the latency of a model request. The standalone judge's median was 2,442ms. Timing is specific to this machine and workload.

The previous recorded cascade selected threshold 8 and flagged 5/48 benign test actions, with 16/16 harmful detections. At the unchanged live threshold 5, that earlier run flagged 6/48. This revision selected 5 on development and flagged 3/48 at that threshold. These are repeated runs of authored scenarios; randomness and prior exposure limit the comparison.

Full evidence: [development](evaluations/inference-20261009T215459Z/dev.json), [test](evaluations/inference-20261009T215459Z/test.json), [frozen input hashes](evaluations/inference-20261009T215459Z/frozen-inputs.json). Re-run `uv run python scripts/evaluate_inference.py` to record a new uniquely named result; expect local model work and preserve prior runs. No result here measures the false-positive rate on unlabelled real traffic.
