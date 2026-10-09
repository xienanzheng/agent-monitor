# Contributing

Keep capture log-only, localhost binding and request-token protection intact. Hook changes belong in the CLI, with backups and explicit installation. Do not attach real agent transcripts, runtime logs, settings or credentials to issues or pull requests. Use synthetic examples.

Run `uv sync --extra dashboard`, `uv run pytest`, `npm test`, and the dashboard tests/build before submitting changes. Browser tests require installed Google Chrome. See the README for commands.

For detection changes, add both a harmful case and an authorized lookalike. Keep development and test pairs together, select thresholds on development data, and record the actual rules, prompt, feature and dataset hashes. Label synthetic findings and missing coverage. Repeated use of the supplied test split is regression testing, not a new unseen benchmark.

Explain the observed problem, resulting behavior and relevant validation in your pull request. Add no real traffic to fixtures. New runtime dependencies must remain compatible with local operation.
