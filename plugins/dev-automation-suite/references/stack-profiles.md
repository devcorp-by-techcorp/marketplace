# Stack Profiles

## Why detection, not assumption

The predecessor suite hard-coded Python/Flask/MongoEngine into its phase
prompts — 45 files referenced Flask, 24 referenced MongoEngine. That capped its
usefulness at one project. `scripts/stack_profile.py` replaces the assumption
with detection against manifests actually present.

## Composition

Profiles compose rather than exclude. A repository holding an Expo app and a
Flask API returns both, because a flattened checklist would blur what "async
error handling" means in an Express route versus a React Native screen. The
`generic` profile is always appended.

## Built-in profiles

| Profile | Detected from | Checks |
|---|---|---|
| `python-flask` | `requirements.txt` / `pyproject.toml` listing Flask, MongoEngine, PyMongo, Django or FastAPI; `app.py` / `wsgi.py` | 7 |
| `typescript-rn` | `package.json` listing `expo` or `react-native`; `app.json` / `eas.json` | 6 |
| `node-express` | `package.json` listing Express/Fastify/Koa, or a SQL client/ORM | 6 |
| `frontend-web` | `package.json` listing React/Vue/Svelte/Next without RN | 3 |
| `generic` | always | 3 |

## Usage

```bash
python3 scripts/stack_profile.py <project_root>              # human-readable
python3 scripts/stack_profile.py <project_root> --json       # machine-readable
python3 scripts/stack_profile.py <project_root> --checklist  # numbered additions
```

`--checklist` emits items numbered from 8, continuing the base seven-item
checklist. Append these to a verification block rather than inventing generic
prose items — concrete, runnable checks are worth more than another bullet.

## Detection reports its own basis

Every profile carries an `evidence` list naming what triggered it. A wrong
profile is visible rather than silent. Detection reads to depth 3 and skips
`node_modules`, `.venv`, `dist`, `build` and similar; in a monorepo, point it at
the subdirectory holding the manifest.

## Adding a profile

1. Add a `_<name>_checks()` builder returning `ProfileCheck` objects. Set
   `security_relevant=True` on items touching a security boundary — the
   verification gate escalates severity on those.
2. Register it in `PROFILE_BUILDERS` with a label and security terms.
3. Add detection evidence in `detect()`, appending to `evidence[<name>]`.
4. Add a test to `tests/test_suite.py::TestStackProfile`.

Keep checks concrete and runnable. Prefer a command (`tsc --noEmit`) over a
prose assertion wherever the environment supports one.
