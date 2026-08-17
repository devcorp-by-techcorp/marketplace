# Agent Team Workflow Packs

This folder contains **task-specific workflow packs** for recurring incidents.

Use these packs when the issue shape is known and you want to launch the right
`/team-*` command sequence quickly with pre-filled context.

## Available workflows

- `live-location-onstreet-data.md` — Persistent bug where live-location street
  display resolves to the same on-street segment (`ROSSLYN STREET between Howard and king`)
  across unrelated patrol areas.

## How to run

1. Open the matching workflow pack.
2. Copy the **Launch Command** section into the current session.
3. Execute phases in order (Debug → Review → Feature/Fix → Validate).
4. Shutdown team resources with `/team-shutdown` after completion.

## Notes

- These packs are additive and do not replace `references/agent-teams-integration.md`.
- Keep workflow packs focused on one recurring incident pattern.
