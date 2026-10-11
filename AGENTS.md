# Agent rules

Read `README.md` and `docs/cozyla-cloud-api.md` first.

Verify:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

CI trust: full — CI runs the same commands.

- Cloud API facts come from decompiled Cozyla apps; record new ones in `docs/cozyla-cloud-api.md` with the app and version they came from.
- Decompiled sources and APKs stay outside the repo.
