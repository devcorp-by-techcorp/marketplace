#!/usr/bin/env python3
"""
Regression tests for the dev-automation-suite.

Run:  python3 tests/test_suite.py

Covers the behaviours that would silently degrade the gate if they broke:
the enforcement rules, registry integrity, stack detection, and the hook's
payload handling (which had a real stdin-collision defect during development).

Standard library only — no pytest dependency, so this runs anywhere the suite
scripts run.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SUITE_ROOT / 'scripts'
HOOKS = SUITE_ROOT / 'hooks'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'

sys.path.insert(0, str(SCRIPTS))

import script_registry as registry  # noqa: E402
import stack_profile  # noqa: E402
import ground_file  # noqa: E402
import work_items  # noqa: E402
import verification_gate as gate  # noqa: E402
import review_packet  # noqa: E402


def run_gate(text: str, **kwargs) -> gate.GateReport:
    return gate.run_gate(text, source='<test>', **kwargs)


TABLE_HEADER = (
    '| # | Check | Status | Evidence | Severity if wrong | Confidence |\n'
    '|---|-------|--------|----------|-------------------|------------|\n'
)


def table(*rows: str) -> str:
    return '## Pre-Output Verification\n\n' + TABLE_HEADER + '\n'.join(rows) + '\n'


class TestEnforcementRules(unittest.TestCase):
    """The rules that make the block a gate rather than decoration."""

    def test_contradicted_blocks(self):
        report = run_gate(table(
            '| 1 | Imports resolve | CONTRADICTED | signature changed | High | High |'
        ))
        self.assertEqual(report.decision, gate.BLOCK)
        self.assertTrue(report.items[0].blocking)

    def test_unverified_on_security_path_blocks(self):
        report = run_gate(table(
            '| 1 | Authorization checks correct | UNVERIFIED | no access to policy service | High | Low |'
        ))
        self.assertEqual(report.decision, gate.BLOCK)

    def test_unverified_off_security_path_is_allowed(self):
        report = run_gate(table(
            '| 1 | Formatting matches style guide | UNVERIFIED | linter unavailable | Low | Low |'
        ))
        self.assertEqual(report.decision, gate.APPROVE)

    def test_status_inflation_downgrades_observed(self):
        report = run_gate(table(
            '| 1 | Referenced APIs are real | OBSERVED | name suggests it exists | High | Medium |'
        ))
        item = report.items[0]
        self.assertEqual(item.reported_status, gate.OBSERVED)
        self.assertEqual(item.effective_status, gate.CLAIMED)
        self.assertEqual(item.evidence_tier, 9)

    def test_observed_on_strong_evidence_is_kept(self):
        report = run_gate(table(
            '| 1 | Types resolve | OBSERVED | tsc --noEmit exit 0 | Medium | High |'
        ))
        self.assertEqual(report.items[0].effective_status, gate.OBSERVED)

    def test_strongest_tier_wins_when_mixed(self):
        report = run_gate(table(
            '| 1 | APIs real | OBSERVED | pytest suite passed; also the naming looked right | High | High |'
        ))
        self.assertEqual(report.items[0].evidence_tier, 2)
        self.assertEqual(report.items[0].effective_status, gate.OBSERVED)

    def test_aggregate_score_invalidates_block(self):
        for phrasing in ('Overall: 6/7 passing', '86% compliant', 'pass rate: 0.86'):
            with self.subTest(phrasing=phrasing):
                report = run_gate(table(
                    '| 1 | Imports resolve | OBSERVED | manifest read | Low | High |'
                ) + '\n' + phrasing + '\n')
                self.assertEqual(report.decision, gate.BLOCK)
                self.assertTrue(
                    any('aggregate' in reason for reason in report.blocking_reasons)
                )

    def test_plain_fail_blocks(self):
        report = run_gate(
            '## Pre-Output Verification\n\n'
            '1. **Imports resolve** — PASS: manifest read.\n'
            '2. **Async error handling** — FAIL: two paths lack a catch.\n'
        )
        self.assertEqual(report.decision, gate.BLOCK)
        self.assertEqual(report.block_format, 'plain')

    def test_missing_block_blocks(self):
        report = run_gate('Everything went fine, shipping now.')
        self.assertEqual(report.decision, gate.BLOCK)
        self.assertEqual(report.block_format, 'unknown')

    def test_min_items_enforced(self):
        report = run_gate(
            table('| 1 | Imports resolve | OBSERVED | manifest read | Low | High |'),
            min_items=7,
        )
        self.assertEqual(report.decision, gate.BLOCK)

    def test_no_aggregate_score_emitted(self):
        report = run_gate(table(
            '| 1 | Imports resolve | OBSERVED | manifest read | Low | High |'
        ))
        serialised = json.dumps(report.__dict__, default=lambda o: o.__dict__)
        for forbidden in ('pass_rate', 'overall_score', 'percentage'):
            self.assertNotIn(forbidden, serialised)


class TestRedaction(unittest.TestCase):
    def test_secret_value_never_reproduced(self):
        secret = 'hunter2supersecretvalue'
        report = run_gate(table(
            f'| 1 | Config check | OBSERVED | JWT_SECRET={secret} at settings.py:14 | High | High |'
        ))
        serialised = json.dumps(report, default=lambda o: o.__dict__)
        self.assertNotIn(secret, serialised)
        self.assertTrue(report.redactions)

    def test_connection_string_redacted(self):
        report = run_gate(table(
            '| 1 | DB config | OBSERVED | mongodb://admin:p4ssw0rd@host/db | High | High |'
        ))
        serialised = json.dumps(report, default=lambda o: o.__dict__)
        self.assertNotIn('p4ssw0rd', serialised)

    def test_clean_evidence_is_not_mangled(self):
        report = run_gate(table(
            '| 1 | Imports resolve | OBSERVED | requirements.txt read | Low | High |'
        ))
        self.assertEqual(report.redactions, [])
        self.assertIn('requirements.txt', report.items[0].evidence)


class TestLimitations(unittest.TestCase):
    def test_missing_limitations_warns_but_does_not_block(self):
        report = run_gate(table(
            '| 1 | Imports resolve | OBSERVED | manifest read | Low | High |'
        ))
        self.assertEqual(report.decision, gate.APPROVE)
        self.assertTrue(any('limitations' in w for w in report.warnings))

    def test_limitations_captured(self):
        report = run_gate(table(
            '| 1 | Imports resolve | OBSERVED | manifest read | Low | High |'
        ) + '\n**Limitations** — no runtime environment available.\n')
        self.assertIn('no runtime environment', report.limitations)


class TestRegistry(unittest.TestCase):
    def test_all_registered_scripts_exist(self):
        self.assertEqual(registry.missing_scripts(), [])

    def test_every_script_compiles(self):
        for spec in registry.REGISTRY.values():
            with self.subTest(script=spec.filename):
                result = subprocess.run(
                    [sys.executable, '-m', 'py_compile', str(spec.path)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_argv_builders_reject_missing_arguments(self):
        with self.assertRaises(registry.RegistryError):
            registry.get('code_review').build_argv(target='x.py')  # no project_root
        with self.assertRaises(registry.RegistryError):
            registry.get('breaking_changes').build_argv(target='x.py')  # no original

    def test_breaking_changes_halts_rather_than_fails(self):
        spec = registry.get('breaking_changes')
        self.assertEqual(spec.interpret_exit(1), registry.HALT)

    def test_self_assessment_exit_two_is_needs_approval(self):
        spec = registry.get('self_assessment')
        self.assertEqual(spec.interpret_exit(2), registry.NEEDS_APPROVAL)

    def test_unknown_script_raises(self):
        with self.assertRaises(registry.RegistryError):
            registry.get('does_not_exist')

    def test_both_lineages_present(self):
        lineages = {spec.lineage for spec in registry.REGISTRY.values()}
        self.assertIn('automate-dev', lineages)
        self.assertIn('production-code-quality', lineages)


class TestStackProfile(unittest.TestCase):
    def _project(self, files: dict[str, str]) -> str:
        tmp = tempfile.mkdtemp()
        for name, content in files.items():
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return tmp

    def test_flask_detected(self):
        root = self._project({'requirements.txt': 'Flask==3.0.0\nmongoengine==0.27\n'})
        report = stack_profile.detect(root)
        self.assertIn('python-flask', report.profile_names)

    def test_expo_detected(self):
        root = self._project({
            'package.json': json.dumps({'dependencies': {'expo': '~51.0.0'}}),
            'app.json': '{}',
        })
        report = stack_profile.detect(root)
        self.assertIn('typescript-rn', report.profile_names)

    def test_profiles_compose(self):
        root = self._project({
            'requirements.txt': 'Flask==3.0.0\n',
            'package.json': json.dumps({'dependencies': {'express': '^4.0.0', 'pg': '^8'}}),
        })
        report = stack_profile.detect(root)
        self.assertIn('python-flask', report.profile_names)
        self.assertIn('node-express', report.profile_names)

    def test_generic_always_present(self):
        root = self._project({'README.md': 'nothing here'})
        report = stack_profile.detect(root)
        self.assertIn('generic', report.profile_names)
        self.assertTrue(report.unmatched)

    def test_malformed_package_json_does_not_crash(self):
        root = self._project({'package.json': '{not valid json'})
        report = stack_profile.detect(root)
        self.assertTrue(any('package.json' in note for note in report.notes))


class TestHook(unittest.TestCase):
    """The hook had a real stdin-collision defect; these pin the fix."""

    HOOK = HOOKS / 'subagent-verification-gate.sh'

    def _run(self, payload: str) -> dict:
        result = subprocess.run(
            ['bash', str(self.HOOK)],
            input=payload, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, 'hook must always exit 0')
        return json.loads(result.stdout)

    def test_clean_block_approved(self):
        text = (FIXTURES / 'clean-evidence-block.md').read_text()
        out = self._run(json.dumps({'agent': 'a', 'output': text}))
        self.assertEqual(out['decision'], 'approve')

    def test_flawed_block_blocked(self):
        text = (FIXTURES / 'flawed-evidence-block.md').read_text()
        out = self._run(json.dumps({'agent': 'a', 'output': text}))
        self.assertEqual(out['decision'], 'block')

    def test_colons_in_output_do_not_truncate(self):
        """The predecessor hook lost everything after the first colon."""
        text = 'Note: at 10:30 I ran: tsc\n\n' + (FIXTURES / 'clean-evidence-block.md').read_text()
        out = self._run(json.dumps({'agent': 'a', 'output': text}))
        self.assertEqual(out['decision'], 'approve')

    def test_raw_non_json_payload(self):
        text = (FIXTURES / 'clean-evidence-block.md').read_text()
        out = self._run(text)
        self.assertEqual(out['decision'], 'approve')

    def test_content_block_list_payload(self):
        text = (FIXTURES / 'clean-evidence-block.md').read_text()
        out = self._run(json.dumps({'output': [{'type': 'text', 'text': text}]}))
        self.assertEqual(out['decision'], 'approve')

    def test_missing_block_blocked(self):
        out = self._run(json.dumps({'agent': 'a', 'output': 'All done, looks good.'}))
        self.assertEqual(out['decision'], 'block')

    def test_empty_payload_approved(self):
        out = self._run('')
        self.assertEqual(out['decision'], 'approve')

    def test_real_subagent_stop_payload_is_read(self):
        """`last_assistant_message` is the field Claude Code actually sends.

        Reading only the synthetic keys made the hook fall through to the raw
        JSON, where the block's headings are escaped text and never match — so
        a perfectly clean delivery was blocked in every real session.
        """
        text = (FIXTURES / 'clean-evidence-block.md').read_text()
        out = self._run(json.dumps({
            'hook_event_name': 'SubagentStop',
            'stop_hook_active': False,
            'agent_type': 'dev-automation-suite:code-reviewer',
            'last_assistant_message': text,
        }))
        self.assertEqual(out['decision'], 'approve')

    def test_real_payload_with_flawed_block_still_blocks(self):
        text = (FIXTURES / 'flawed-evidence-block.md').read_text()
        out = self._run(json.dumps({
            'hook_event_name': 'SubagentStop',
            'last_assistant_message': text,
        }))
        self.assertEqual(out['decision'], 'block')

    def test_stop_hook_active_never_blocks_twice(self):
        """Claude Code allows 8 consecutive blocks; a subagent that cannot emit
        a block should cost one round, not eight."""
        out = self._run(json.dumps({
            'hook_event_name': 'SubagentStop',
            'stop_hook_active': True,
            'agent_type': 'Explore',
            'last_assistant_message': 'All done, looks good.',
        }))
        self.assertEqual(out['decision'], 'approve')

    def test_no_aggregate_score_in_hook_output(self):
        text = (FIXTURES / 'flawed-evidence-block.md').read_text()
        out = self._run(json.dumps({'agent': 'a', 'output': text}))
        self.assertNotIn('scores', out)
        self.assertNotIn('overall', json.dumps(out).lower().replace('overall:', ''))


class TestPluginManifest(unittest.TestCase):
    """The manifest and hook wiring must match the Claude Code plugin spec."""

    MANIFEST = SUITE_ROOT / '.claude-plugin' / 'plugin.json'

    def setUp(self):
        self.manifest = json.loads(self.MANIFEST.read_text())

    def test_manifest_is_valid_json_with_required_name(self):
        self.assertIn('name', self.manifest)
        self.assertRegex(self.manifest['name'], r'^[a-z0-9]+(-[a-z0-9]+)*$',
                         'name must be kebab-case with no spaces')

    def test_claude_plugin_dir_holds_only_manifest_files(self):
        """Spec: plugin.json and marketplace.json belong here; components never do.

        The rule is about component directories, not about the count of files.
        commands/, agents/, skills/ and hooks/ inside .claude-plugin/ load as
        nothing at all, silently.
        """
        entries = sorted(p.name for p in (SUITE_ROOT / '.claude-plugin').iterdir())
        self.assertTrue(set(entries) <= {'plugin.json', 'marketplace.json'}, entries)
        for forbidden in ('commands', 'agents', 'skills', 'hooks', 'scripts'):
            self.assertFalse(
                (SUITE_ROOT / '.claude-plugin' / forbidden).exists(),
                f'{forbidden}/ must live at the plugin root, not in .claude-plugin/',
            )

    def test_component_dirs_are_at_plugin_root(self):
        for name in ('agents', 'commands', 'hooks', 'scripts', 'bin'):
            self.assertTrue((SUITE_ROOT / name).is_dir(), f'{name}/ must be at plugin root')

    def test_skill_md_at_root_for_single_skill_autoload(self):
        skill = SUITE_ROOT / 'SKILL.md'
        self.assertTrue(skill.is_file())
        self.assertFalse((SUITE_ROOT / 'skills').exists(),
                         'a skills/ dir would suppress root SKILL.md autoload')
        self.assertNotIn('skills', self.manifest,
                         'no skills field, so root SKILL.md autoloads as the single skill')
        self.assertRegex(skill.read_text(), r'(?m)^name:\s*dev-automation-suite$')

    def test_hook_command_quotes_plugin_root(self):
        """Unquoted ${CLAUDE_PLUGIN_ROOT} breaks on cache paths containing spaces."""
        hooks = json.loads((SUITE_ROOT / 'hooks' / 'hooks.json').read_text())
        command = hooks['hooks']['SubagentStop'][0]['hooks'][0]['command']
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}"', command)

    def test_hook_matcher_scopes_to_this_plugin_s_agents(self):
        """SubagentStop matches on agent_type, and `*` matches every one of them.

        The gate demands a verification block the built-in agents know nothing
        about, so an unscoped matcher blocks Explore and general-purpose in
        every session the plugin is enabled for — the plugin's own contract
        applied to agents that never agreed to it.
        """
        import re
        hooks = json.loads((SUITE_ROOT / 'hooks' / 'hooks.json').read_text())
        matcher = hooks['hooks']['SubagentStop'][0]['matcher']
        self.assertNotEqual(matcher, '*')
        pattern = re.compile(matcher)
        for agent in ('code-explorer', 'code-architect', 'code-reviewer'):
            for name in (agent, f'dev-automation-suite:{agent}'):
                self.assertTrue(pattern.search(name), name)
        for outsider in ('Explore', 'Plan', 'general-purpose', 'statusline-setup'):
            self.assertFalse(pattern.search(outsider), outsider)

    def test_hook_matcher_covers_every_bundled_agent(self):
        """An agent added to agents/ but not the matcher is silently ungated."""
        import re
        hooks = json.loads((SUITE_ROOT / 'hooks' / 'hooks.json').read_text())
        pattern = re.compile(hooks['hooks']['SubagentStop'][0]['matcher'])
        for agent in (SUITE_ROOT / 'agents').glob('*.md'):
            name = re.search(r'(?m)^name:\s*(\S+)', agent.read_text()).group(1)
            with self.subTest(agent=name):
                self.assertTrue(pattern.search(f'dev-automation-suite:{name}'), name)

    def test_agent_models_are_pinned_not_aliased(self):
        """`opus`/`sonnet` re-point on release, changing a gate's behaviour
        without changing a line of this package."""
        import re
        for agent in (SUITE_ROOT / 'agents').glob('*.md'):
            model = re.search(r'(?m)^model:\s*(\S+)', agent.read_text()).group(1)
            with self.subTest(agent=agent.name):
                self.assertNotIn(model, {'opus', 'sonnet', 'haiku'})
                self.assertRegex(model, r'^claude-[a-z]+-\d')

    def test_hook_script_is_executable(self):
        import os
        script = SUITE_ROOT / 'hooks' / 'subagent-verification-gate.sh'
        self.assertTrue(os.access(script, os.X_OK), 'hook must be chmod +x')

    def test_bin_wrappers_are_executable(self):
        import os
        wrappers = list((SUITE_ROOT / 'bin').iterdir())
        self.assertTrue(wrappers)
        for wrapper in wrappers:
            self.assertTrue(os.access(wrapper, os.X_OK), f'{wrapper.name} must be chmod +x')

    def test_bin_wrappers_resolve_and_run(self):
        result = subprocess.run(
            ['bash', str(SUITE_ROOT / 'bin' / 'dev-suite'), 'phases'],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('bootstrap', result.stdout)

    def test_agent_frontmatter_uses_supported_fields(self):
        supported = {
            'name', 'description', 'model', 'effort', 'maxTurns', 'tools',
            'disallowedTools', 'skills', 'memory', 'background', 'isolation',
            'color',
        }
        forbidden = {'hooks', 'mcpServers', 'permissionMode'}
        for agent in (SUITE_ROOT / 'agents').glob('*.md'):
            with self.subTest(agent=agent.name):
                lines = agent.read_text().split('---')[1].strip().splitlines()
                keys = {ln.split(':', 1)[0].strip() for ln in lines if ':' in ln
                        and not ln.startswith(' ')}
                self.assertFalse(keys & forbidden,
                                 f'{keys & forbidden} not permitted for plugin agents')
                self.assertTrue(keys <= supported, f'unexpected keys: {keys - supported}')

    def test_commands_have_description_frontmatter(self):
        for command in (SUITE_ROOT / 'commands').glob('*.md'):
            with self.subTest(command=command.name):
                self.assertRegex(command.read_text(), r'(?m)^description:\s*\S')


class TestGroundFile(unittest.TestCase):
    """Premise tracking: type is an audit trail, tier is confidence."""

    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        self.pid = 'test/project'

    def _ground(self):
        return ground_file.load(self.pid, self.store)

    def test_type_is_immutable_no_api_path_changes_it(self):
        g = self._ground()
        item = ground_file.add(g, 'DB', 'Uses Postgres', ground_file.INFERRED)
        ground_file.set_tier(g, item.id, ground_file.ESTABLISHED)
        self.assertEqual(item.type, ground_file.INFERRED)
        self.assertEqual(item.tier, ground_file.ESTABLISHED)

    def test_invalid_type_rejected(self):
        g = self._ground()
        with self.assertRaises(ground_file.GroundError):
            ground_file.add(g, 'X', 'Y', 'guessed')

    def test_high_impact_defaults_to_open(self):
        g = self._ground()
        item = ground_file.add(g, 'Auth model', 'RBAC permission checks',
                               ground_file.INFERRED)
        self.assertEqual(item.tier, ground_file.OPEN)

    def test_low_impact_inferred_defaults_to_working(self):
        g = self._ground()
        item = ground_file.add(g, 'Formatter', 'Prettier is used',
                               ground_file.INFERRED)
        self.assertEqual(item.tier, ground_file.WORKING)

    def test_uncertain_always_opens(self):
        g = self._ground()
        item = ground_file.add(g, 'Formatter', 'Maybe prettier', ground_file.UNCERTAIN)
        self.assertEqual(item.tier, ground_file.OPEN)

    def test_open_high_impact_premise_blocks(self):
        g = self._ground()
        ground_file.add(g, 'Auth model', 'RBAC checks', ground_file.UNCERTAIN)
        findings = ground_file.check(g)
        self.assertTrue(any(f.blocking for f in findings))

    def test_open_low_impact_warns_but_does_not_block(self):
        g = self._ground()
        ground_file.add(g, 'Formatter', 'Prettier maybe', ground_file.UNCERTAIN)
        findings = ground_file.check(g)
        self.assertTrue(findings)
        self.assertFalse(any(f.blocking for f in findings))

    def test_established_on_assumed_derivation_is_flagged(self):
        g = self._ground()
        item = ground_file.add(g, 'Coverage', '80% target', ground_file.ASSUMED)
        ground_file.set_tier(g, item.id, ground_file.ESTABLISHED)
        findings = ground_file.check(g)
        self.assertTrue(any('derivation' in f.message for f in findings))

    def test_validate_all_skips_open_items(self):
        """An unanswered question must not become current by being timestamped."""
        g = self._ground()
        open_item = ground_file.add(g, 'SSR', 'Needs SSR', ground_file.UNCERTAIN)
        ground_file.add(g, 'Formatter', 'Prettier', ground_file.INFERRED)
        ground_file.validate_all(g)
        self.assertEqual(open_item.last_validated, '')

    def test_round_trip_persists_both_representations(self):
        g = self._ground()
        ground_file.add(g, 'DB', 'Uses Postgres', ground_file.INFERRED)
        md, index = ground_file.save(g, self.store)
        self.assertTrue(md.is_file() and index.is_file())
        reloaded = ground_file.load(self.pid, self.store)
        self.assertEqual(len(reloaded.assumptions), 1)
        self.assertEqual(reloaded.assumptions[0].type, ground_file.INFERRED)

    def test_type_maps_onto_gate_status_vocabulary(self):
        g = self._ground()
        item = ground_file.add(g, 'X', 'Y', ground_file.ASSUMED)
        self.assertEqual(item.gate_status, 'CLAIMED')

    def test_missing_ground_file_yields_empty_not_error(self):
        g = ground_file.load('never/seen', self.store)
        self.assertEqual(g.assumptions, [])


class TestPremiseCrossCheck(unittest.TestCase):
    """The gate must catch work that is correct about code but built on sand."""

    def _block(self, check_text):
        return table(f'| 1 | {check_text} | OBSERVED | source read directly | High | High |')

    def test_item_on_open_high_impact_premise_blocks(self):
        premises = [{
            'id': 'A2', 'title': 'Auth model', 'assumption': 'RBAC permission checks',
            'high_impact': True, 'terms': ['permission', 'rbac', 'checks'],
        }]
        report = gate.run_gate(
            self._block('RBAC permission checks applied to route'),
            premises=premises,
        )
        self.assertEqual(report.decision, gate.BLOCK)
        self.assertTrue(report.premise_findings)

    def test_item_on_open_low_impact_premise_warns_only(self):
        premises = [{
            'id': 'A5', 'title': 'Formatter', 'assumption': 'prettier formatting',
            'high_impact': False, 'terms': ['prettier', 'formatting'],
        }]
        report = gate.run_gate(
            self._block('prettier formatting applied'), premises=premises)
        self.assertEqual(report.decision, gate.APPROVE)
        self.assertTrue(report.premise_findings)

    def test_unrelated_premise_does_not_match(self):
        premises = [{
            'id': 'A9', 'title': 'Deployment', 'assumption': 'kubernetes cluster',
            'high_impact': True, 'terms': ['kubernetes', 'cluster'],
        }]
        report = gate.run_gate(self._block('Imports resolve'), premises=premises)
        self.assertEqual(report.decision, gate.APPROVE)
        self.assertEqual(report.premise_findings, [])

    def test_single_term_overlap_is_not_enough(self):
        """One shared word is coincidence, not a reference."""
        premises = [{
            'id': 'A1', 'title': 'Checks', 'assumption': 'something',
            'high_impact': True, 'terms': ['checks', 'kubernetes'],
        }]
        report = gate.run_gate(self._block('checks applied'), premises=premises)
        self.assertEqual(report.decision, gate.APPROVE)

    def test_premises_absent_leaves_behaviour_unchanged(self):
        report = gate.run_gate(self._block('Imports resolve'))
        self.assertEqual(report.decision, gate.APPROVE)
        self.assertEqual(report.premise_findings, [])


class TestWorkItems(unittest.TestCase):
    """Local file-based tracking. No external service, markdown is the truth."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        work_items.write_index(self.root)
        self.epic = work_items.create_epic(self.root, 'Test epic')

    def _ticket(self, title, **kw):
        return work_items.create_ticket(self.root, self.epic.id, title, **kw)

    def test_markdown_is_source_of_truth(self):
        self._ticket('One', acceptance=['works'], body='Do the thing')
        loaded = work_items.load_all(self.root)
        self.assertEqual(len(loaded[0].tickets), 1)
        self.assertEqual(loaded[0].tickets[0].acceptance, ['works'])

    def test_unknown_dependency_rejected(self):
        with self.assertRaises(work_items.WorkItemError):
            self._ticket('Bad', depends_on=['T-999'])

    def test_out_of_order_start_rejected(self):
        self._ticket('First', acceptance=['a'], body='b')
        self._ticket('Second', depends_on=['T-1'], acceptance=['a'], body='b')
        with self.assertRaises(work_items.WorkItemError):
            work_items.set_status(self.root, 'T-2', work_items.IN_PROGRESS)

    def test_order_allowed_once_dependency_done(self):
        self._ticket('First', acceptance=['a'], body='b')
        self._ticket('Second', depends_on=['T-1'], acceptance=['a'], body='b')
        work_items.set_status(self.root, 'T-1', work_items.DONE)
        ticket = work_items.set_status(self.root, 'T-2', work_items.IN_PROGRESS)
        self.assertEqual(ticket.status, work_items.IN_PROGRESS)

    def test_waves_group_independent_tickets(self):
        self._ticket('A', acceptance=['x'], body='y')
        self._ticket('B', acceptance=['x'], body='y')
        self._ticket('C', depends_on=['T-1'], acceptance=['x'], body='y')
        epic = work_items.find_epic(self.root, self.epic.id)
        grouped = work_items.waves(epic)
        self.assertEqual({t.id for t in grouped[0]}, {'T-1', 'T-2'})
        self.assertEqual([t.id for t in grouped[1]], ['T-3'])

    def test_dependency_cycle_raises_not_arbitrary_order(self):
        self._ticket('A', acceptance=['x'], body='y')
        self._ticket('B', depends_on=['T-1'], acceptance=['x'], body='y')
        # Introduce the cycle directly on disk
        path = work_items.work_dir(self.root) / self.epic.id / 'T-1.md'
        path.write_text(path.read_text().replace(
            'depends_on: []', 'depends_on: [T-2]'), encoding='utf-8')
        epic = work_items.find_epic(self.root, self.epic.id)
        with self.assertRaises(work_items.WorkItemError) as ctx:
            work_items.waves(epic)
        self.assertIn('cycle', str(ctx.exception))

    def test_gaps_name_the_actual_cause(self):
        no_body = self._ticket('One', acceptance=['works'])
        self.assertEqual(len(no_body.gaps), 1)
        self.assertIn('description', no_body.gaps[0])
        neither = self._ticket('Two')
        self.assertEqual(len(neither.gaps), 2)
        complete = self._ticket('Three', acceptance=['works'], body='Do it')
        self.assertEqual(complete.gaps, [])
        self.assertTrue(complete.self_contained)

    def test_next_ready_respects_dependencies(self):
        self._ticket('A', acceptance=['x'], body='y')
        self._ticket('B', depends_on=['T-1'], acceptance=['x'], body='y')
        epic = work_items.find_epic(self.root, self.epic.id)
        self.assertEqual([t.id for t in work_items.next_ready(epic)], ['T-1'])

    def test_index_is_derived_and_labelled_as_such(self):
        self._ticket('A', acceptance=['x'], body='y')
        index = json.loads((work_items.work_dir(self.root) / 'index.json').read_text())
        self.assertIn('Derived', index['note'])


def _find_marketplace():
    """Locate the catalog that lists this plugin.

    The marketplace manifest belongs at the root of the repository that hosts
    the plugin, not inside the plugin — `source` paths in it are resolved
    relative to its own directory, so a manifest sitting beside the plugin's
    own files can only ever describe the plugin as `./`. Walk up to find it so
    the suite still tests correctly when vendored under a different root.
    """
    for candidate in [SUITE_ROOT, *SUITE_ROOT.parents]:
        manifest = candidate / '.claude-plugin' / 'marketplace.json'
        if manifest.is_file():
            return manifest
    return None


class TestMarketplaceManifest(unittest.TestCase):
    """The hosting repository's catalog must point at this plugin correctly."""

    MARKETPLACE = _find_marketplace()

    #: Names reserved for official Anthropic use. A third-party marketplace using
    #: one fails to load as registered from an untrusted source.
    RESERVED = {
        'claude-code-marketplace', 'claude-code-plugins', 'claude-plugins-official',
        'claude-plugins-community', 'claude-community', 'anthropic-marketplace',
        'anthropic-plugins', 'agent-skills', 'anthropic-agent-skills',
        'knowledge-work-plugins', 'life-sciences', 'claude-for-legal',
        'claude-for-financial-services', 'financial-services-plugins',
        'first-party-plugins', 'healthcare',
    }
    #: Rejected by Claude Desktop's managed marketplace sync, in any casing.
    DESKTOP_REJECTED = {'org', 'org-provisioned', 'unknown'}

    def setUp(self):
        if self.MARKETPLACE is None:
            self.skipTest('no marketplace.json in any ancestor directory')
        self.mk = json.loads(self.MARKETPLACE.read_text())
        self.root = self.MARKETPLACE.parent.parent
        self.entry = next(e for e in self.mk['plugins'] if e['name'] == 'dev-automation-suite')

    def test_required_fields_present(self):
        for key in ('name', 'owner', 'plugins'):
            self.assertIn(key, self.mk)
        self.assertIn('name', self.mk['owner'])
        self.assertTrue(self.mk['plugins'])

    def test_marketplace_name_is_not_reserved(self):
        self.assertNotIn(self.mk['name'].lower(), self.RESERVED)

    def test_marketplace_name_not_rejected_by_desktop(self):
        self.assertNotIn(self.mk['name'].lower(), self.DESKTOP_REJECTED)
        self.assertRegex(self.mk['name'], r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')

    def test_names_are_kebab_case(self):
        """claude.ai marketplace sync rejects non-kebab-case names."""
        self.assertRegex(self.mk['name'], r'^[a-z0-9]+(-[a-z0-9]+)*$')
        for entry in self.mk['plugins']:
            self.assertRegex(entry['name'], r'^[a-z0-9]+(-[a-z0-9]+)*$')

    def test_no_duplicate_plugin_names(self):
        names = [e['name'] for e in self.mk['plugins']]
        self.assertEqual(len(names), len(set(names)))

    def test_entry_name_matches_plugin_manifest(self):
        """A mismatch installs the plugin under a slug its own manifest disowns."""
        manifest = json.loads((SUITE_ROOT / '.claude-plugin' / 'plugin.json').read_text())
        self.assertEqual(self.entry['name'], manifest['name'])

    def test_version_declared_in_exactly_one_place(self):
        """plugin.json silently wins, so a version in both lets a stale one mask the other."""
        manifest = json.loads((SUITE_ROOT / '.claude-plugin' / 'plugin.json').read_text())
        self.assertIn('version', manifest)
        self.assertNotIn('version', self.entry)

    def test_relative_sources_resolve_and_avoid_traversal(self):
        for entry in self.mk['plugins']:
            source = entry['source']
            if isinstance(source, str):
                self.assertTrue(source.startswith('./'), source)
                self.assertNotIn('..', source)
                resolved = (self.root / source).resolve()
                self.assertTrue(resolved.is_dir(), resolved)

    def test_entry_source_points_at_this_plugin(self):
        """A source resolving anywhere else installs an empty plugin, silently.

        `./` — the plugin's own directory when the manifest sat beside it —
        resolves to the repository root once the manifest moves there, and the
        root holds no agents/, commands/ or SKILL.md to load.
        """
        self.assertEqual((self.root / self.entry['source']).resolve(), SUITE_ROOT)

    def test_entry_source_holds_a_plugin_manifest(self):
        manifest = (self.root / self.entry['source']).resolve() / '.claude-plugin' / 'plugin.json'
        self.assertTrue(manifest.is_file(), manifest)

    def test_renames_entries_terminate(self):
        """Every chain must end at null or a listed plugin, with no cycles."""
        renames = self.mk.get('renames', {})
        listed = {e['name'] for e in self.mk['plugins']}
        for start in renames:
            seen, current = set(), start
            while current is not None and current not in listed:
                self.assertNotIn(current, seen, f'rename cycle at {current}')
                seen.add(current)
                self.assertIn(current, renames, f'{current} terminates nowhere')
                current = renames[current]


class TestReviewPacket(unittest.TestCase):
    """A reviewer that reads the author's account is not reviewing."""

    TASK = 'Uploads are timing out for some users.'
    DIFF = ('--- a/upload.py\n+++ b/upload.py\n@@\n'
            '+MAX_RETRIES = 3\n+def upload(f): ...\n')

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.record = review_packet.record_task(str(self.root), self.TASK)

    def _packet(self, **overrides):
        return review_packet.build_packet(
            overrides.get('record', self.record), overrides.get('work', self.DIFF))

    # -- the clean path ----------------------------------------------------

    def test_built_packet_is_clean(self):
        self.assertEqual(review_packet.check_packet(self._packet(), self.record), [])

    def test_packet_contains_task_and_work_only(self):
        headings = [h for _, h in review_packet.headings(self._packet().splitlines())]
        self.assertEqual(headings, ['## Task', '## Work'])

    # -- the task is quoted, not restated ----------------------------------

    def test_restated_task_is_caught(self):
        """The framing failure this module exists for: an orchestrator that
        compresses the request into an already-decided sentence."""
        leading = self._packet().replace(
            self.TASK, 'Review the retry logic added to fix the upload race.')
        rules = {f.rule for f in review_packet.check_packet(leading, self.record)}
        self.assertIn('task_tampering', rules)

    def test_self_consistent_paraphrase_is_still_caught(self):
        """The realistic attack, and the one the header alone misses.

        An orchestrator that builds its own packet computes a correct hash of
        its own paraphrase, so the packet is internally consistent. Only the
        comparison against the task recorded before work began catches it.
        """
        forged = dict(self.record)
        forged['task'] = 'Review the retry logic added to fix the upload race.'
        forged['sha256'] = review_packet.sha256(forged['task'])
        packet = review_packet.build_packet(forged, self.DIFF)

        self.assertEqual(review_packet.check_packet(packet), [],
                         'internally consistent — the header check cannot see this')
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('task_tampering', rules)

    def test_task_edit_is_caught_without_the_recorded_original(self):
        """A packet from elsewhere is still checkable: the header pins the hash."""
        edited = self._packet().replace(self.TASK, 'Fix the upload race condition.')
        rules = {f.rule for f in review_packet.check_packet(edited)}
        self.assertIn('task_tampering', rules)

    def test_recording_a_different_task_is_refused(self):
        """A task re-recorded mid-work is the author's summary of what they built."""
        with self.assertRaises(ValueError):
            review_packet.record_task(str(self.root), 'Add retry logic to uploads.')

    def test_recording_the_same_task_is_idempotent(self):
        again = review_packet.record_task(str(self.root), self.TASK)
        self.assertEqual(again['sha256'], self.record['sha256'])

    # -- prose contamination ----------------------------------------------

    def test_author_narrative_is_caught(self):
        packet = self._packet() + '\nI chose exponential backoff for this.\n'
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('author_narrative', rules)

    def test_self_assessment_is_caught(self):
        packet = self._packet() + '\nAll tests pass, ready for merge.\n'
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('self_assessment', rules)

    def test_authors_verification_block_is_caught(self):
        packet = self._packet() + '\n## Pre-Output Verification\n\nchecked\n'
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('verification_block', rules)

    def test_process_reference_is_caught(self):
        packet = self._packet() + '\nSee .dev-suite/logs/session.log for context.\n'
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('process_reference', rules)

    def test_extra_section_is_caught(self):
        packet = self._packet() + '\n## Notes for the reviewer\n\ncontext\n'
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('extra_section', rules)

    # -- the checker must not eat correct packets --------------------------

    def test_markdown_headings_in_the_task_do_not_break_the_packet(self):
        """A bug report opening with `## Steps to reproduce` is an ordinary
        task. Unfenced, its headings read as packet structure and the build
        fails closed on a request that was recorded exactly right."""
        task = ('Uploads time out.\n\n## Steps to reproduce\n\n'
                '1. Upload a 2GB file\n\n## Work already tried\n\nRaising the timeout.')
        root = Path(tempfile.mkdtemp())
        record = review_packet.record_task(str(root), task)
        packet = review_packet.build_packet(record, self.DIFF)
        self.assertEqual(review_packet.check_packet(packet, record), [])

    def test_a_task_containing_its_own_fence_is_wrapped_in_a_longer_one(self):
        """Tasks get pasted out of issue trackers, code blocks and all. A fixed
        three-backtick wrapper is closed by the first one of those."""
        task = 'Uploads time out.\n\n```python\nupload(big)\n```'
        root = Path(tempfile.mkdtemp())
        record = review_packet.record_task(str(root), task)
        packet = review_packet.build_packet(record, self.DIFF)
        self.assertIn('````text', packet)
        self.assertEqual(review_packet.check_packet(packet, record), [])

    def test_a_diff_touching_markdown_does_not_break_the_packet(self):
        work = ('--- a/README.md\n+++ b/README.md\n@@\n'
                '+## Install\n+\n+```bash\n+pip install x\n+```\n')
        packet = review_packet.build_packet(self.record, work)
        self.assertEqual(review_packet.check_packet(packet, self.record), [])

    def test_swapped_work_is_caught(self):
        """Declaring a hash and never checking it reads as integrity that is
        not enforced. The realistic case is staleness, not tampering: a packet
        built early, work continued, packet never rebuilt."""
        packet = self._packet().replace('+MAX_RETRIES = 3', '+MAX_RETRIES = 999')
        rules = {f.rule for f in review_packet.check_packet(packet, self.record)}
        self.assertIn('work_tampering', rules)

    def test_narrative_shaped_code_is_not_flagged(self):
        """The diff is the artifact. Scanning it for words *about* the artifact
        is how a checker like this starts rejecting correct packets."""
        noisy = ('--- a/x.py\n+++ b/x.py\n@@\n'
                 '+# I decided on a token bucket; all tests pass.\n'
                 '+STATUS = "OBSERVED"\n'
                 '+def my_approach(): ...\n')
        packet = review_packet.build_packet(self.record, noisy)
        self.assertEqual(review_packet.check_packet(packet, self.record), [])

    def test_build_refuses_work_carrying_narrative_outside_the_fence(self):
        with self.assertRaises(ValueError):
            review_packet.build_packet(self.record, '   ')

    def test_missing_section_is_caught(self):
        rules = {f.rule for f in review_packet.check_packet('## Task\n\nsomething\n')}
        self.assertIn('missing_section', rules)

    def test_no_recorded_task_is_an_explicit_failure(self):
        with self.assertRaises(FileNotFoundError):
            review_packet.load_task(str(Path(tempfile.mkdtemp())))


class TestTokenBudgetTags(unittest.TestCase):
    """`--tag` attribution, ported forward from automate-dev v1.1.0.

    The suite dropped tags when it dropped agent-teams. Bringing the subsystem
    back brings the requirement back with it: `agent-teams-integration.md` and
    `token-budgeting.md` both invoke `--tag team:<name>`, and without it a team
    run cannot be costed apart from the phase it ran inside.
    """

    MONITOR = SCRIPTS / 'token_budget_monitor.py'

    def _run(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(self.MONITOR), *args],
            capture_output=True, text=True, timeout=60,
        )
        self.assertIn(result.returncode, (0, 2), result.stderr)
        return json.loads(result.stdout)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        subprocess.run(
            [sys.executable, str(self.MONITOR), 'init', self.root,
             '--difficulty', 'medium'],
            capture_output=True, text=True, check=True,
        )

    def test_tag_accumulates_across_records_and_models(self):
        first = self._run('record', self.root, '--phase', 'review',
                          '--tokens', '1000', '--model', 'claude-opus-5',
                          '--tag', 'team:review-team')
        self.assertEqual(first['tag'], 'team:review-team')
        self.assertEqual(first['tag_total'], 1000)

        second = self._run('record', self.root, '--phase', 'review',
                           '--tokens', '500', '--model', 'claude-sonnet-5',
                           '--tag', 'team:review-team')
        self.assertEqual(second['tag_total'], 1500)

        by_tag = self._run('summary', self.root)['by_tag']['team:review-team']
        self.assertEqual(by_tag['tokens'], 1500)
        self.assertEqual(by_tag['invocations'], 2)
        self.assertEqual(by_tag['by_model'],
                         {'claude-opus-5': 1000, 'claude-sonnet-5': 500})

    def test_untagged_record_emits_no_tag_keys(self):
        """A caller that passed no --tag sees no tag keys, not nulls."""
        out = self._run('record', self.root, '--phase', 'test', '--tokens', '100')
        self.assertEqual([k for k in out if 'tag' in k], [])

    def test_summary_filters_to_one_tag(self):
        for phase, tag in (('review', 'team:review-team'), ('build', 'team:build-team')):
            self._run('record', self.root, '--phase', phase, '--tokens', '100',
                      '--tag', tag)
        self.assertEqual(
            sorted(self._run('summary', self.root)['by_tag']),
            ['team:build-team', 'team:review-team'])
        self.assertEqual(
            list(self._run('summary', self.root, '--tag', 'team:build-team')['by_tag']),
            ['team:build-team'])

    def test_port_left_pricing_and_default_model_intact(self):
        """The port must not disturb what the suite version added over v1.1.0."""
        sys.path.insert(0, str(SCRIPTS))
        import token_budget_monitor as monitor
        self.assertEqual(monitor.DEFAULT_MODEL, 'claude-opus-5')
        for model in ('claude-opus-5', 'claude-sonnet-5'):
            self.assertIn(model, monitor.MODEL_PRICING)


class TestReviewerIsolation(unittest.TestCase):
    """The packet controls what the reviewer is handed; this controls what it
    can reach. A reviewer given a clean packet that can open the author's
    session log has been handed nothing and told everything."""

    HOOK = HOOKS / 'reviewer-isolation.sh'

    def _run(self, payload: dict) -> dict:
        result = subprocess.run(
            ['bash', str(self.HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def _decision(self, payload: dict) -> str:
        out = self._run(payload)
        return out.get('hookSpecificOutput', {}).get('permissionDecision', 'allow')

    def _pre(self, tool: str, tool_input: dict, agent='dev-automation-suite:code-reviewer'):
        return {'hook_event_name': 'PreToolUse', 'agent_type': agent,
                'tool_name': tool, 'tool_input': tool_input}

    def test_reviewer_cannot_read_suite_state(self):
        self.assertEqual(
            self._decision(self._pre('Read', {'file_path': '/p/.dev-suite/logs/a.log'})),
            'deny')

    def test_reviewer_cannot_read_an_agent_transcript(self):
        self.assertEqual(
            self._decision(self._pre(
                'Read', {'file_path': '/home/u/.claude/projects/x/subagents/a.jsonl'})),
            'deny')

    def test_reviewer_cannot_shell_into_the_process_record(self):
        self.assertEqual(
            self._decision(self._pre('Bash', {'command': 'cat .dev-suite/logs/*.log'})),
            'deny')

    def test_reviewer_keeps_the_codebase(self):
        """Reviewing a diff means reading the code around it."""
        self.assertEqual(
            self._decision(self._pre('Read', {'file_path': '/p/src/upload.py'})),
            'allow')

    def test_reviewer_keeps_a_shell_for_tests(self):
        self.assertEqual(
            self._decision(self._pre('Bash', {'command': 'python3 -m pytest tests/'})),
            'allow')

    def test_windows_separators_do_not_bypass_the_denylist(self):
        """A forward-slash rule never matches a backslash path, and the call
        proceeds as though the hook had not run."""
        self.assertEqual(
            self._decision(self._pre(
                'Read', {'file_path': 'C:\\proj\\.dev-suite\\logs\\a.log'})),
            'deny')

    def test_grep_glob_cannot_reach_the_process_record(self):
        """`glob` is a location and `path` is a location, but Grep's `pattern`
        is a regex. A key-name denylist that ignores the difference lets
        `Grep(glob=".dev-suite/**")` read the session while Read and Bash are
        blocked."""
        self.assertEqual(
            self._decision(self._pre(
                'Grep', {'pattern': 'secret', 'glob': '.dev-suite/**'})),
            'deny')

    def test_grepping_for_the_string_is_still_allowed(self):
        """The mirror-image error: blocking a reviewer from searching the source
        for the literal text, which is ordinary review of this very plugin."""
        self.assertEqual(
            self._decision(self._pre(
                'Grep', {'pattern': r'\.dev-suite', 'path': 'scripts'})),
            'allow')

    def test_glob_pattern_is_a_location(self):
        self.assertEqual(
            self._decision(self._pre('Glob', {'pattern': '.dev-suite/**/*.json'})),
            'deny')

    def test_an_unrecognised_tool_fails_closed(self):
        """A file-reading tool added later must not pass silently."""
        self.assertEqual(
            self._decision(self._pre('SomeNewReader', {'glob': '.dev-suite/**'})),
            'deny')

    def test_other_agents_are_untouched(self):
        self.assertEqual(
            self._decision(self._pre(
                'Read', {'file_path': '/p/.dev-suite/logs/a.log'}, agent='Explore')),
            'allow')

    def test_contract_is_injected_at_spawn(self):
        """So the contract does not depend on the orchestrator including it."""
        out = self._run({'hook_event_name': 'SubagentStart',
                         'agent_type': 'dev-automation-suite:code-reviewer',
                         'agent_id': 'a1'})
        context = out['hookSpecificOutput']['additionalContext']
        self.assertIn('independently', context)
        self.assertIn('report the contamination', context)

    def test_malformed_payload_does_not_wedge_the_session(self):
        result = subprocess.run(
            ['bash', str(self.HOOK)], input='not json',
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)


class TestBlindReviewWiring(unittest.TestCase):
    """The two phases where one agent judges another's output."""

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        import suite_orchestrator
        self.orch = suite_orchestrator

    def test_review_and_validate_require_a_packet(self):
        for phase in (3, 7):
            with self.subTest(phase=phase):
                self.assertTrue(self.orch.PHASES[phase].requires_review_packet)

    def test_producing_phases_do_not(self):
        """Build and Fix are agent-led but not reviewing — the agent is
        producing work, not judging someone else's."""
        for phase in (2, 5):
            with self.subTest(phase=phase):
                self.assertFalse(self.orch.PHASES[phase].requires_review_packet)

    def test_missing_packet_halts_the_phase(self):
        result = self.orch.run_phase(3, project_root=tempfile.mkdtemp())
        packet_checks = [c for c in result.checks if c.script == 'review_packet']
        self.assertEqual(len(packet_checks), 1)
        self.assertEqual(packet_checks[0].verdict, 'HALT')

    def test_contaminated_packet_halts_rather_than_routing_to_fix(self):
        """There is nothing to fix in the code — the review was never conducted
        under the conditions it claims."""
        spec = registry.get('review_packet')
        self.assertTrue(spec.halts_on_fail)
        self.assertEqual(spec.interpret_exit(1), 'HALT')

    def test_reviewer_has_no_tool_that_reads_another_agent_s_output(self):
        import re
        text = (SUITE_ROOT / 'agents' / 'code-reviewer.md').read_text()
        tools = re.search(r'(?m)^tools:\s*(.+)$', text).group(1)
        for forbidden in ('BashOutput', 'KillShell'):
            self.assertNotIn(forbidden, tools)

    def test_workflow_ships_and_declares_its_name(self):
        workflow = SUITE_ROOT / 'workflows' / 'independent-review.js'
        self.assertTrue(workflow.is_file())
        source = workflow.read_text()
        self.assertIn("name: 'independent-review'", source)
        self.assertNotIn('import(', source,
                         'the workflow runtime rejects a script containing import()')


class TestPythonFloorIsReal(unittest.TestCase):
    """The package advertises Python 3.8+. That claim is only worth making if
    something checks it — annotations are evaluated at definition time, so
    `def f() -> list[str]` raises TypeError on 3.8 and nothing here would
    notice until a user on an old interpreter hit it.
    """

    #: PEP 585 builtin generics: `list[str]` is a runtime subscript of the
    #: builtin, valid from 3.9. Under `from __future__ import annotations`
    #: every annotation is a string and never evaluated, so 3.8 is fine.
    PEP_585 = {'list', 'dict', 'tuple', 'set', 'frozenset', 'type'}

    def _annotations(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arg_list = list(node.args.args) + list(node.args.kwonlyargs)
                arg_list += list(getattr(node.args, 'posonlyargs', []))
                for arg in arg_list:
                    if arg.annotation is not None:
                        yield arg.annotation
                if node.returns is not None:
                    yield node.returns
            elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                yield node.annotation

    def _offending(self, annotation):
        """Constructs that are evaluated at definition time and fail on 3.8."""
        for node in ast.walk(annotation):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                if node.value.id in self.PEP_585:
                    return f'{node.value.id}[...] (PEP 585, needs 3.9)'
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                return 'X | Y union (PEP 604, needs 3.10)'
        return None

    def test_modern_annotations_are_postponed(self):
        for path in sorted((SUITE_ROOT / 'scripts').glob('*.py')):
            source = path.read_text()
            tree = ast.parse(source)
            postponed = any(
                isinstance(n, ast.ImportFrom) and n.module == '__future__'
                and any(a.name == 'annotations' for a in n.names)
                for n in tree.body
            )
            if postponed:
                continue
            with self.subTest(script=path.name):
                for annotation in self._annotations(tree):
                    offence = self._offending(annotation)
                    self.assertIsNone(
                        offence,
                        f'{path.name}:{annotation.lineno} uses {offence} without '
                        "`from __future__ import annotations`. It is evaluated at "
                        'definition time and raises TypeError on the advertised '
                        'floor. Add the future import, or change the floor.',
                    )

    def test_advertised_floor_matches_the_ci_matrix(self):
        """A README that says 3.8 and a matrix that starts at 3.11 is a claim
        nobody tests."""
        import re
        workflow = (SUITE_ROOT.parent.parent / '.github' / 'workflows' / 'ci.yml')
        if not workflow.is_file():
            self.skipTest('no CI workflow in this checkout')
        text = workflow.read_text()
        advertised = re.search(
            r'Python (\d+\.\d+)\+', (SUITE_ROOT / 'SKILL.md').read_text())
        self.assertIsNotNone(advertised, 'SKILL.md states no Python floor')
        self.assertIn(f"'{advertised.group(1)}'", text,
                      'the advertised floor is not in the CI matrix')


if __name__ == '__main__':
    unittest.main(verbosity=2)
