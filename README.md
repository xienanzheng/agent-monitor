# Agent Monitor

Local monitoring for coding-agent tool activity. Python captures and evaluates actions; React presents evidence, sessions and incidents. Models run through your local Ollama server.

![Investigation dashboard using a synthetic replay](docs/walkthrough/live.png)

The hooks record activity and fail open. Assessments run asynchronously and do not block agent actions. Claude Code capture is verified; Codex has an adapter and requires its own hook installation. General ChatGPT conversations are not automatically captured.

## Download and run

The npm distribution includes the Python source, rules, prompts, synthetic cases, tests and a built dashboard. Python dependencies and model weights are installed separately. It requires Node 22+, Python 3.11+ through [uv](https://docs.astral.sh/uv/getting-started/installation/), and [Ollama](https://ollama.com). macOS and Linux are supported; use WSL on Windows. macOS notifications are optional. The code is MIT licensed; dependencies and separately downloaded models retain their own licenses.

Download directly from the public GitHub repository:

```sh
npx --yes github:xienanzheng/agent-monitor init my-monitor
cd my-monitor
npm run setup
ollama pull qwen3:4b
ollama pull qwen3:8b
npm start
```

After npm registry publication, the shorter download command is available:

```sh
npx @xienanzheng/agent-monitor init my-monitor
```

Start Ollama before launching. Open http://127.0.0.1:8765. Ctrl-C stops the daemon and dashboard started by this command. Startup after reboot is manual.

For a source download or clone, enter its directory and start at `npm run setup`. The built release includes dashboard assets; a development checkout needs `npm run build:dashboard` first. `npm install` does not install hooks or download model weights.

## Enable capture

```sh
npm run doctor
npm run monitor -- install-hooks --agent claude
```

Installation backs up Claude settings. Restart open Claude sessions, then perform a harmless action and verify events appear. The dashboard distinguishes configured hooks from observed activity.

Codex installation is separate: `npm run monitor -- install-hooks --agent codex`. Follow the CLI's native hook-approval instructions. To roll back, run `npm run monitor -- uninstall-hooks --agent claude --backup '<path printed during installation>'` and restart sessions.

## How it works

Hooks normalize and redact events, then send them through a private Unix socket. If the daemon is unavailable, they spool to disk. The daemon correlates requests and outputs by tool-call ID, applies action/sequence rules, and sends cases needing interpretation to local Qwen3 4B triage and Qwen3 8B review.

Rules see 20 recent actions; model context contains up to five recent actions and available outputs. Severity 5 opens an incident and 8 can trigger a notification. Scores and self-reported confidence are judgments, not probabilities of harm.

Live, Sessions, Incidents, Explore, Evaluation and Rules provide investigation views. Tool output, rule evidence, authorization, affected boundary and recoverability remain separate. Pending reviews and failed reviews are distinct. Incomplete judgments retain rule evidence.

## Privacy and limitations

Local model requests go to localhost. Redaction is pattern-based and best effort; review evidence before sharing it. Runtime logs, real traffic, local results and machine settings are excluded from this release. Hook coverage and model correctness remain imperfect. Public data transfer, credential transfer and writing a command example require different interpretations.

The evaluation uses authored synthetic trajectories, fixed paired development/test splits and thresholds selected on development data. Synthetic results measure regression behavior, not real-world safety. Unlabelled real traffic measures alert volume, not false-positive rate.

Read the [architecture and research rationale](docs/architecture.md), [recorded results and limitations](docs/evaluation.md), [screenshot walkthrough](docs/walkthrough.md), and [release procedure](docs/releasing.md).

## Development

```sh
uv sync --extra dashboard
uv run pytest
npm test
npm --prefix dashboard ci
npm --prefix dashboard test
npm --prefix dashboard run e2e
```

Browser tests use installed Google Chrome. Frontend building requires Node; serving the built dashboard uses Python. The source includes the synthetic dataset and a frozen-run evaluator at `scripts/evaluate_inference.py`.
