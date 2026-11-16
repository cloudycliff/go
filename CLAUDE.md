# Claude Code / agent notes

Read `docs/progress.md` (decisions, status, next steps) and `docs/design-v1.md` before working.

- Commit as `cloudycliff <cloudycliff@gmail.com>` (set in this repo's git config) and push to `origin main`
  after every change.
- Never commit `config.toml` (has the Fox nickname), `models/` (large model files), `logs/` or any API key.
  LLM keys go in environment variables only.
- Python: standard library only; run `python -m unittest discover -s tests` before committing.
- Reference code (read-only): `C:\src\go\lizzieyzy-next` (GPL-3.0; reuse ideas, do not copy code) and
  the portable release `C:\src\go\LizzieYzy Next NVIDIA` whose `katago.exe` and weights the pipeline uses.
- Update `docs/progress.md` when a milestone or decision changes.
