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


if __name__ == '__main__':
    unittest.main(verbosity=2)
