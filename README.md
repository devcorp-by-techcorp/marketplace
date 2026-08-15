# techcorp-plugins

TechCorp's internal Claude Code plugin marketplace.

## Install

```bash
claude plugin marketplace add devcorp-by-techcorp/marketplace
claude plugin install dev-automation-suite@techcorp-plugins
```

From a local checkout, add the **repository root** — not the plugin directory.
`source` paths in `marketplace.json` resolve relative to the manifest, so
pointing at the plugin directory finds no marketplace at all:

```bash
claude plugin marketplace add /path/to/marketplace
```

Hook and agent changes need `/reload-plugins` or a restart.

## Plugins

| Plugin | What it does |
|---|---|
| [`dev-automation-suite`](plugins/dev-automation-suite) | Autonomous development across an eleven-phase lifecycle with script-enforced quality gates. Blocks unverified agent deliveries at `SubagentStop`, halts on breaking changes and unvalidated premises, rejects band-aid fixes, and detects the project stack instead of assuming it. Python 3.8+ standard library and Bash only — no third-party packages, no external services. |

## Layout

```
.claude-plugin/marketplace.json     the catalog — one entry per plugin
plugins/<name>/
  .claude-plugin/plugin.json        the plugin's own manifest
  SKILL.md  agents/  commands/  hooks/  scripts/  bin/  references/  tests/
```

Two rules account for most of what goes wrong here:

- **The marketplace manifest belongs at the repository root, the plugin
  manifest inside the plugin.** A `marketplace.json` sitting beside a plugin's
  own files can only ever describe that plugin as `./`, which resolves to
  whatever directory the manifest is in.
- **Component directories live at the plugin root, never inside
  `.claude-plugin/`.** A `commands/` or `agents/` directory under
  `.claude-plugin/` loads as nothing at all, and says nothing about it.

## Adding a plugin

1. Create `plugins/<name>/` with a `.claude-plugin/plugin.json` and whatever
   components it ships.
2. `chmod +x` every file in `bin/` and every hook script, and confirm the mode
   survived into git — `git ls-files -s` should show `100755`, not `100644`.
   A stripped executable bit is invisible locally and fatal after a clone.
3. Add an entry to `.claude-plugin/marketplace.json` with
   `"source": "./plugins/<name>"`.
4. Validate before pushing:

```bash
claude plugin validate ./plugins/<name>
```

Version lives in the plugin's own `plugin.json`, not in the marketplace entry.
Declaring it in both lets a stale value mask the other — `plugin.json` wins
silently.
