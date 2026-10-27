#!/usr/bin/env python3
"""Build new, sanitized repository evidence from retained native JSON receipts.

No remote calls, no host mutations, no credentials copied. The output directory
must be new unless --refresh updates this generator's two own files. Nested
process.text/result.stdout JSON and JSON-lines are decoded;
the success of a shell wrapper is never treated as product acceptance.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

HOSTS = ('sentinela-a', 'sentinela-b', 'sentinela-c', 'sentinela-d',
         'nucleo-a', 'ninja-blue', 'observer', 'storage', 'services')
AGENT_SHA = 'ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d'
STD = 'hara-commander-agent.service'
V2 = 'hara-commander-agent-v2.service'
FLEET_SCHEMA = 'hara.commander.private-fleet-update-0356.v1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decoded(value, depth=0):
    if depth > 18:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from decoded(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from decoded(child, depth + 1)
    elif isinstance(value, str) and len(value) < 4 * 1024**2:
        try:
            child = json.loads(value)
        except (ValueError, TypeError):
            for line in value.splitlines():
                if line.lstrip().startswith(('{', '[')):
                    try:
                        yield from decoded(json.loads(line), depth + 1)
                    except (ValueError, TypeError):
                        pass
        else:
            yield from decoded(child, depth + 1)


def timestamp(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.timestamp() if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def fresh_heartbeat(runtime):
    start = timestamp(runtime.get('started_at_utc'))
    heartbeat = timestamp(runtime.get('last_successful_heartbeat_at_utc'))
    return start is not None and heartbeat is not None and heartbeat >= start


def safe_error(value):
    value = str(value or '')
    code = value.split(':', 1)[0]
    return code if re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', code) else ('RECORDED_ERROR_REDACTED' if value else None)


def service_fields(value):
    if isinstance(value, dict):
        return value
    return dict(x.split('=', 1) for x in str(value or '').splitlines() if '=' in x)


def mapping(value):
    return value if isinstance(value, dict) else {}


class Evidence:
    def __init__(self, source):
        self.source = Path(source)
        self.rows = []
        self.sources = {}
        self.capture_mtime = {}
        self.errors = []
        prefixes = ('sentinela-', 'nucleo-', 'ninja-', 'observer-', 'storage-', 'services-')
        names = {'native-linux-evidence.json', 'private-signature-verification.json',
                 'fleet-contracts-ready.json', 'first-push-receipt.json',
                 'private-distribution-closeout.json', 'startup-fix-native-tests-contracts.json',
                 'windows-login-final-readback.json'}
        for path in sorted(self.source.glob('*.json')):
            if path.name not in names and not path.name.startswith(prefixes) and not path.name.startswith('fleet-process-'):
                continue
            raw = path.read_bytes()
            if len(raw) > 4 * 1024**2:
                self.errors.append({'source': path.name, 'code': 'SOURCE_TOO_LARGE'})
                continue
            self.sources[path.name] = {'sha256': digest(raw), 'bytes': len(raw)}
            self.capture_mtime[path.name] = path.stat().st_mtime_ns
            try:
                value = json.loads(raw)
            except (ValueError, TypeError):
                self.errors.append({'source': path.name, 'code': 'SOURCE_JSON_INCOMPLETE'})
                continue
            self.rows.extend((path.name, row) for row in decoded(value))

    def find(self, predicate):
        return [(name, row) for name, row in self.rows if predicate(row)]

    def ref(self, name):
        return {'retained_source_name': name, **self.sources[name]}

    def native(self, host):
        candidates = self.find(lambda x: x.get('schema') == FLEET_SCHEMA and
                               x.get('target') == host and 'state' in x)
        attempts = []
        seen = set()
        for name, row in sorted(candidates, key=lambda x: timestamp(x[1].get('finished_at') or x[1].get('started_at')) or 0):
            key = digest(json.dumps(row, sort_keys=True).encode())
            if key in seen:
                continue
            seen.add(key)
            runtime = row.get('runtime', {})
            units = row.get('units_after', {})
            standard, v2 = units.get(STD, {}), units.get(V2, {})
            success = (row.get('state') == 'PASS_PRIVATE_0356_RUNTIME_MIGRATION' and
                       row.get('updater_exit') == 0 and runtime.get('agent_version') == '0.3.56' and
                       runtime.get('agent_sha256') == AGENT_SHA and fresh_heartbeat(runtime) and
                       standard.get('active') is True and v2.get('active') is False and
                       v2.get('enabled') in ('disabled', 'not-found') and row.get('event_v2') == 'OFF' and
                       row.get('enrollment_or_trust_config_changed') is False)
            attempts.append({'state': 'PASS' if success else ('HOLD' if row.get('finished_at') else 'IN_PROGRESS'),
                             'native_state': row.get('state'), 'started_at': row.get('started_at'),
                             'finished_at': row.get('finished_at'), 'updater_exit': row.get('updater_exit'),
                             'error_code': safe_error(row.get('error')),
                             'rollback_state': row.get('rollback', {}).get('state'),
                             'rollback_error_code': safe_error(row.get('rollback', {}).get('error')),
                             'runtime': {k: runtime.get(k) for k in ('agent_version', 'agent_sha256', 'pid',
                                         'started_at_utc', 'last_successful_heartbeat_at_utc')},
                             'fresh_heartbeat': fresh_heartbeat(runtime),
                             'one_active_standard_v2_stopped': success,
                             'standard_enabled': standard.get('enabled'), 'v2_enabled': v2.get('enabled'),
                             'configuration_preserved': True if success else None,
                             'event_v2': row.get('event_v2'), 'evidence': self.ref(name)})
        if attempts:
            return {'state': attempts[-1]['state'], 'method': 'FINITE_MIGRATION_HELPER',
                    'latest': attempts[-1], 'attempts': attempts}
        direct = self.find(lambda x: x.get('host') == host and isinstance(x.get('update'), dict) and 'runtime' in x)
        if not direct:
            return {'state': 'PENDING_EVIDENCE', 'attempts': []}
        direct.sort(key=lambda x: timestamp(x[1].get('at_utc') or x[1].get('started_at_utc')) or 0)
        name, row = direct[-1]
        update, runtime = row['update'], row['runtime']
        tokens = set(update.get('out', '').splitlines())
        agent_sha = row.get('agent_sha256') or row.get('after_hashes', {}).get('agent')
        service = service_fields(row.get('service'))
        okay = (update.get('rc') == 0 and 'HARA_COMMANDER_AGENT_UPDATE=PASS' in tokens and
                'HARA_COMMANDER_AGENT_INTEGRITY=PASS' in tokens and agent_sha == AGENT_SHA and
                runtime.get('agent_version') == '0.3.56' and fresh_heartbeat(runtime) and
                service.get('ActiveState') == 'active' and service.get('SubState') == 'running')
        before = row.get('before_hashes')
        if not before:
            before_rows = [r.get('before_hashes') for _, r in direct if r.get('before_hashes')]
            before = before_rows[0] if before_rows else {}
        after = row.get('after_hashes') or {'config': row.get('config_sha256'), 'unit': row.get('unit_sha256')}
        config_preserved = bool(before.get('config') and before.get('config') == after.get('config'))
        unit_preserved = bool(before.get('unit') and before.get('unit') == after.get('unit'))
        rollback_preserved = bool(before.get('agent') and row.get('rollback_sha256') == before.get('agent'))
        okay = okay and config_preserved and unit_preserved and rollback_preserved
        result = {'state': 'PASS' if okay else 'HOLD', 'updater_exit': update.get('rc'),
                  'observed_at': row.get('at_utc'), 'agent_sha256': agent_sha,
                  'agent_version': runtime.get('agent_version'), 'pid': int(service.get('MainPID', 0)),
                  'started_at_utc': runtime.get('started_at_utc'),
                  'last_successful_heartbeat_at_utc': runtime.get('last_successful_heartbeat_at_utc'),
                  'fresh_heartbeat': fresh_heartbeat(runtime), 'standard_enabled': service.get('UnitFileState'),
                  'configuration_preserved': config_preserved, 'unit_file_preserved': unit_preserved,
                  'rollback_matches_preimage': rollback_preserved,
                  'rollback_sha256': row.get('rollback_sha256'), 'evidence': self.ref(name)}
        return {'state': result['state'], 'method': 'OFFICIAL_UPDATER_WITH_REVIEWED_CLI_MIGRATION',
                'latest': result, 'attempts': [result]}

    def e2e(self, host):
        records = self.find(lambda x: x.get('computer') == host and
                            mapping(x.get('result')).get('function_id') == 'device.info')
        if not records:
            return {'state': 'PENDING_EVIDENCE'}
        # MCP device.info receipts have no event timestamp. Preserve that limit;
        # use the most recently retained capture, not lexicographic filenames.
        name, record = max(records, key=lambda x: self.capture_mtime[x[0]])
        result = record['result']
        try:
            info = json.loads(result.get('stdout', ''))
        except ValueError:
            info = {}
        passed = (record.get('state') == 'PASS' and result.get('process_exit_code') == 0 and
                  info.get('agent_version') == '0.3.56' and info.get('approval_mode') == 'PERSISTENT_TRUSTED')
        return {'state': 'PASS' if passed else 'HOLD', 'function': 'device.info',
                'agent_version': info.get('agent_version'), 'approval_mode': info.get('approval_mode'),
                'transport': info.get('tunnel_mode'), 'process_exit_code': result.get('process_exit_code'),
                'architecture': info.get('architecture'), 'agent_python_version': info.get('python_version'),
                'selection_basis': 'MOST_RECENT_RETAINED_CAPTURE_FILE_MTIME_NOT_TOOL_EVENT_TIME',
                'receipt_sha256': record.get('bridge_receipt_sha256'), 'evidence': self.ref(name)}

    def nucleo_incident(self):
        rows = self.find(lambda x: x.get('host') == 'nucleo-a' and x.get('update', {}).get('rc') == 7 and
                         'HARA_COMMANDER_CLI_PATH_CONFLICT' in x.get('update', {}).get('err', ''))
        if not rows:
            return {'state': 'NOT_IN_INPUT'}
        name, row = rows[0]
        before, after = row.get('before_hashes', {}), row.get('after_hashes', {})
        restored = bool(before.get('agent') and before == after and row.get('rollback_sha256') == before['agent'])
        return {'state': 'PASS_OBSERVED_FILE_COMPENSATION' if restored else 'HOLD',
                'first_update_exit': 7, 'cause': 'LEGACY_CLI_SYMLINK_CONFLICT',
                'agent_config_unit_hashes_restored': restored,
                'restored_agent_sha256': after.get('agent'),
                'service_after_failure': service_fields(row.get('service')).get('ActiveState'),
                'runtime_version_after_failure': row.get('runtime', {}).get('agent_version'),
                'scope': 'File rollback after installer CLI conflict; not a crash/reboot/recovery campaign.',
                'evidence': self.ref(name)}

    def process_e2e(self, host):
        rows = self.find(lambda x: x.get('computer') == host and mapping(x.get('result')).get('function_id') == 'process.run')
        if not rows:
            return {'state': 'PENDING_EVIDENCE'}
        name, row = max(rows, key=lambda x: self.capture_mtime[x[0]])
        result = row['result']
        try:
            process = json.loads(result.get('stdout', ''))
        except ValueError:
            process = {}
        text = process.get('text', '').strip()
        okay = (row.get('state') == 'PASS' and result.get('process_exit_code') == 0 and
                process.get('command_preview') == 'id -u' and process.get('exit_code') == 0 and
                process.get('timed_out') is False and process.get('output_truncated') is False and
                text.isdecimal() and result.get('local_authorization_mode') == 'PERSISTENT_TRUSTED')
        return {'state': 'PASS' if okay else 'HOLD', 'function': 'process.run', 'command': 'id -u',
                'returned_uid': int(text) if text.isdecimal() else None, 'process_exit_code': process.get('exit_code'),
                'authorization_mode': result.get('local_authorization_mode'),
                'authorization_source': result.get('authorization_source'),
                'receipt_sha256': row.get('bridge_receipt_sha256'), 'evidence': self.ref(name)}

    def startup_fix(self):
        tests = []
        for name, row in self.find(lambda x: 'tests_rc' in x and isinstance(x.get('inventory'), dict)):
            host = row['inventory'].get('target')
            log = str(row.get('tests_out', '')) + str(row.get('tests_err', ''))
            count = re.search(r'\bRan (\d+) tests? in ', log)
            passed = row['tests_rc'] == 0 and bool(re.search(r'^OK\s*$', log, re.M)) and count and int(count[1]) == 8
            tests.append({'host': host, 'state': 'PASS' if passed else 'HOLD', 'exit': row['tests_rc'],
                          'tests': int(count[1]) if count else None, 'skips_reported': 'skipped' in log.lower(),
                          'inventory_exit': row.get('inventory_rc'), 'contract_sha256': row.get('contract_sha256'),
                          'evidence': self.ref(name)})
        source_dir = Path(__file__).parent
        files = {}
        for filename in ('fleet_update_private_0356.py', 'test_fleet_update_private_0356_startup.py'):
            path = source_dir / filename
            if path.is_file():
                data = path.read_bytes()
                files[filename] = {'sha256': digest(data), 'bytes': len(data)}
        return {'state': 'PASS_NATIVE_TESTS_BOTH_HOSTS' if {r['host'] for r in tests if r['state'] == 'PASS'} == {'storage', 'sentinela-b'} else 'PENDING_OR_HOLD',
                'prior_helper_sha256': '80f726cbf2340406917c3864e3ec440af73459ea826580736f747c891b674866',
                'reviewed_source_files': files, 'native_tests': tests,
                'scope': 'Post-start ACTIVE_AGENT_CMDLINE observation retry only, <=5s and bounded by existing deadline; inventory and path/hash validation remain strict.'}

    def windows(self):
        records = [(n, r) for n, r in self.rows if n == 'windows-login-final-readback.json' and
                   'console_user' in r and isinstance(r.get('qa_profiles'), list)]
        if not records:
            return {'state': 'NOT_IN_INPUT'}
        name, row = records[-1]
        loaded = sum(mapping(profile).get('Loaded') is True for profile in row['qa_profiles'])
        return {'state': 'HOLD_NO_SIGNED_IN_QA_CONTEXT' if not row.get('console_user') and loaded == 0 else 'CONTEXT_REQUIRES_REVIEW',
                'console_user_present': bool(row.get('console_user')), 'qa_profiles_observed': len(row['qa_profiles']),
                'qa_profiles_loaded': loaded, 'installation_acceptance': 'NOT_PROVEN_BY_THIS_READBACK',
                'evidence': self.ref(name)}

    def distribution_closeout(self):
        rows = [(n, r) for n, r in self.rows if n == 'private-distribution-closeout.json' and
                r.get('state') == 'PASS_PRIVATE_DISTRIBUTION_CLOSED']
        if not rows:
            return {'state': 'PENDING_EVIDENCE'}
        name, row = rows[-1]
        flags = ('listener_absent', 'ufw_active', 'temporary_ufw_rules_absent',
                 'qa_guard_original_rules_restored', 'temporary_nft_rule_absent')
        commands = ('server_stop', 'firewall_cleanup', 'timer_stop')
        okay = all(row.get(k) is True for k in flags) and all(mapping(row.get(k)).get('rc') == 0 for k in commands)
        return {'state': 'PASS_PRIVATE_DISTRIBUTION_CLOSED' if okay else 'HOLD', 'at_utc': row.get('at_utc'),
                **{k: row.get(k) for k in flags}, 'command_exits': {k: mapping(row.get(k)).get('rc') for k in commands},
                'evidence': self.ref(name)}

    def storage_restoration(self):
        baselines = self.find(lambda x: x.get('target') == 'storage' and 'files' in x and 'configuration' in x)
        afters = [(n, r) for n, r in self.rows if n == 'storage-after-held-migration.json' and
                  all(k in r for k in ('agent', 'config', 'unit', 'dropin', 'runtime', 'service'))]
        if not baselines or not afters:
            return {'state': 'NOT_IN_INPUT'}
        baseline_name, baseline = baselines[0]
        name, after = afters[-1]
        checks = {k: after[k].get('sha256') == baseline['files'][b].get('sha256') for k, b in
                  (('agent', 'agent'), ('config', 'config'), ('unit', 'standard_unit'))}
        checks['dropin_absent'] = after['dropin'].get('exists') is False
        checks['cli_restored'] = after.get('cli_target') == baseline['files']['cli'].get('target')
        service = service_fields(after['service'])
        checks['old_runtime_active'] = service.get('ActiveState') == 'active' and after['runtime'].get('agent_version') == '0.3.54'
        checks['old_runtime_fresh_heartbeat'] = fresh_heartbeat(after['runtime'])
        return {'state': 'PASS_READBACK_RESTORATION' if all(checks.values()) else 'HOLD', 'checks': checks,
                'runtime_version': after['runtime'].get('agent_version'),
                'interpretation': 'Observed helper startup-readback race; updater exit was 0. No .56 product defect established.',
                'evidence': self.ref(name), 'baseline_evidence': self.ref(baseline_name)}

    def ubuntu(self):
        rows = self.find(lambda x: all(k in x for k in ('cold_restore', 'update', 'native_start')))
        if not rows:
            return {'state': 'NOT_IN_INPUT'}
        name, row = rows[0]
        cold, native = row['cold_restore'], row['native_start']
        update = row.get('update', {}).get('update', {})
        runtime = native.get('runtime', {})
        return {'cold_restore_state': cold.get('state'), 'baseline_version': cold.get('baseline_version'),
                'cold_checkpoint_sha256': cold.get('checkpoint', {}).get('sha256'),
                'update_exit': update.get('rc'), 'update_pass': 'HARA_COMMANDER_AGENT_UPDATE=PASS' in update.get('out', '').splitlines(),
                'updater_preserved_manual_stop': 'HARA_COMMANDER_AGENT_UPDATE_RUNTIME_ATTESTATION=SKIPPED_MANUAL_STOP' in update.get('out', '').splitlines(),
                'installed_agent_sha256': native.get('files', {}).get('agent', {}).get('sha256'),
                'runtime_agent_version': runtime.get('agent_version'), 'native_start_exit': native.get('start', {}).get('rc'),
                'started_at_utc': runtime.get('started_at_utc'),
                'last_successful_heartbeat_at_utc': runtime.get('last_successful_heartbeat_at_utc'),
                'fresh_heartbeat': fresh_heartbeat(runtime), 'remote_operation': 'NOT_PROVEN_BY_THIS_RECORD',
                'old_r2_campaign_reopened': cold.get('old_campaign_reopened'), 'evidence': self.ref(name)}

    def build(self):
        hosts = [{'host': host, 'native': self.native(host), 'commander_e2e': self.e2e(host),
                  'process_execution_e2e': self.process_e2e(host)} for host in HOSTS]
        native_count = sum(x['native']['state'] == 'PASS' for x in hosts)
        e2e_count = sum(x['commander_e2e']['state'] == 'PASS' for x in hosts)
        signed = self.find(lambda x: x.get('signature_verified') is True and x.get('version') == '0.3.56')
        signing = {'state': 'NOT_IN_INPUT'}
        if signed:
            name, row = signed[0]
            signing = {'state': 'PASS_VERIFIED_PRIVATE_SIGNATURE', **{k: row.get(k) for k in
                       ('manifest_sha256', 'signature_sha256', 'public_jwk_sha256', 'kid', 'rsa_bits_observed')},
                       'evidence': self.ref(name)}
        git = []
        for name, row in self.find(lambda x: 'verified_destination' in x and 'ref' in x):
            match = re.fullmatch(r'([0-9a-f]{40})\s+refs/heads/(\S+)', row['ref'])
            if match:
                destination = 'GitHub' if row['verified_destination'] == 'https://github.com/tiagoharalabs/hara-site.git' else 'Storage origin'
                git.append({'destination': destination, 'commit': match[1], 'branch': match[2], 'evidence': self.ref(name)})
        return {'schema': 'hara.commander.private-fleet-rollout-evidence.v1',
                'generator_sha256': digest(Path(__file__).read_bytes()),
                'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'scope': 'Observed private Linux rollout; no public launch approval.', 'candidate_version': '0.3.56',
                'linux_agent_sha256': AGENT_SHA, 'physical_hosts_expected': len(HOSTS),
                'native_pass_count': native_count, 'commander_device_info_pass_count': e2e_count,
                'commander_id_u_pass_count': sum(x['process_execution_e2e']['state'] == 'PASS' for x in hosts),
                'rollout_state': 'PASS_ALL_NINE_NATIVE_AND_E2E' if native_count == e2e_count == len(HOSTS) else 'IN_PROGRESS_OR_HOLD',
                'public_release': 'NO_GO_NOT_ESTABLISHED_BY_THIS_ROLLOUT', 'hosts': hosts,
                'nucleo_cli_conflict_and_file_rollback': self.nucleo_incident(),
                'nucleo_process_execution_e2e': self.process_e2e('nucleo-a'),
                'storage_first_attempt_restoration': self.storage_restoration(),
                'helper_startup_race_fix': self.startup_fix(), 'windows_qa_user_context': self.windows(),
                'private_distribution_closeout': self.distribution_closeout(),
                'ubuntu_qa_vm': self.ubuntu(), 'private_signature': signing, 'git_verified_checkpoints': git,
                'limits': ['Windows native installation/acceptance is not established by these Linux records.',
                           'Ubuntu QA historical heartbeat is not fresh remote liveness.',
                           'The prior R2 STOP is preserved; R10 diagnostic tests are not a restore PASS.',
                           'Product recovery/resilience gates and ChatGPT OAuth refresh require their own evidence.',
                           'No public release, Store submission, security-audit closure or Event V2 enablement is claimed.'],
                'input_errors': self.errors,
                'sanitization': 'Explicit field selection only; no raw command output, device token, configuration bytes, private keys or session data copied.'}


def markdown(report):
    nucleo_compensated = report['nucleo_cli_conflict_and_file_rollback']['state'] == 'PASS_OBSERVED_FILE_COMPENSATION'
    by_host = {row['host']: row for row in report['hosts']}
    nucleo_retry = by_host['nucleo-a']['native']['state'] == 'PASS'
    storage_restored = report['storage_first_attempt_restoration']['state'] == 'PASS_READBACK_RESTORATION'
    storage_retry = by_host['storage']['native']['state'] == 'PASS'
    process = report['nucleo_process_execution_e2e']
    closeout = report['private_distribution_closeout']
    lines = ['# Commander 0.3.56 — atualização privada da frota', '',
             'Gerado em ' + report['generated_at_utc'] + '.', '',
             f"**Resultado observado:** {report['native_pass_count']}/9 hosts com atualização e runtime nativos aprovados; "
             f"{report['commander_device_info_pass_count']}/9 com `device.info` pelo Commander principal na versão .56.", '',
             f"Execução remota de `id -u`: **{report['commander_id_u_pass_count']}/9 PASS**, com exit0 e autorização `PERSISTENT_TRUSTED` por política do enrollment.", '',
             '**Lançamento público: NO-GO.** Este registro comprova a execução privada descrita e não aprova publicação.', '',
             '## Resultado por host', '', '| Host | Instalação/runtime | Commander E2E | Início da .56 | Heartbeat posterior |',
             '|---|---|---|---|---|']
    for host in report['hosts']:
        row = host['native'].get('latest', {})
        runtime = row.get('runtime', row)
        lines.append('| ' + ' | '.join((host['host'], host['native']['state'], host['commander_e2e']['state'],
                                      str(runtime.get('started_at_utc') or '—'), 'Sim' if row.get('fresh_heartbeat') else 'Não comprovado')) + ' |')
    lines += ['', 'Os hosts migrados pelo helper convergem para a unidade standard; onde a unidade V2 já existia, ela permanece preservada para rollback, parada e desabilitada após o health. '
              'O opt-in legado da V2 não é transferido. O updater conserva o enrollment e as cópias de rollback, com verificação própria por host.', '',
              '## Ocorrências e provas adicionais', '',
              '- **Nucleo-A:** a primeira tentativa retornou rc7 por conflito com a CLI legada. ' +
              ('A comparação dos hashes confirmou a compensação: Agent, configuração e unidade preservados, com o serviço .54 ativo. ' if nucleo_compensated else 'A comprovação da compensação está pendente. ') +
              ('Após a migração explícita da CLI, a segunda tentativa concluiu a atualização e o runtime .56 com PASS, seguidos de E2E. ' if nucleo_retry else 'A retentativa ainda não tem PASS. ') +
              'A primeira falha permanece no registro.',
              '- **Processo real no Nucleo-A:** ' +
              ('`process.run` executou `id -u`, retornou UID ' + str(process['returned_uid']) + ', com exit0 e autorização `PERSISTENT_TRUSTED`.' if process['state'] == 'PASS' else 'Ainda não comprovado neste corte.'),
              '- **Storage:** a primeira tentativa terminou HOLD por `ACTIVE_AGENT_CMDLINE` durante a observação imediatamente após o start; o updater havia retornado exit0. ' +
              ('O readback independente confirmou restauração dos arquivos, configuração, unidade e CLI, remoção do drop-in e serviço .54 ativo com heartbeat novo. ' if storage_restored else 'A restauração independente ainda precisa de comprovação. ') +
              ('Com o fix do helper, a retentativa 02 concluiu a migração .56 com PASS e E2E. ' if storage_retry else 'A retentativa ainda não tem PASS. ') +
              'A primeira HOLD continua registrada. A corrida observada pertence ao helper; não demonstra defeito do produto .56.', '',
              'O fix do helper aguarda somente a observação transitória `ACTIVE_AGENT_CMDLINE` após o start, por até 5 s e dentro do deadline existente. '
              'A identidade do executável permanece obrigatória. O JSON vincula os hashes das fontes e os 8 testes dirigidos nativos em cada um de Storage e Sentinela B.', '',
              '## VM Ubuntu e limites', '',
              'A VM Ubuntu tem evidência de checkpoint frio, restauração materializada e boot da baseline pelo libvirt normal, seguida do update oficial .56. '
              'O updater preservou o estado manualmente parado. Um start nativo posterior não transforma um heartbeat histórico em prova de operação remota.', '',
              'O readback Windows mais recente está registrado separadamente: usuário de console presente = ' + str(report['windows_qa_user_context'].get('console_user_present')) +
              '; perfis QA carregados = ' + str(report['windows_qa_user_context'].get('qa_profiles_loaded')) + '. Essa leitura não comprova instalação nem aceitação Windows.', '',
              'A aceitação Windows, a recuperação funcional do produto, o refresh OAuth ponta a ponta, os gates de segurança e a publicação continuam exigindo evidências próprias. '
              'O R2 anterior permanece STOP; testes do R10 não são promovidos a aceite de restore. Event V2 não é habilitado nesta rodada.', '',
              '## Encerramento da distribuição privada', '',
              'Estado: **' + closeout['state'] + '**, observado em ' + str(closeout.get('at_utc', 'não registrado')) + '. ' +
              ('O servidor e o timer foram parados; o listener e as regras temporárias UFW/nft estão ausentes. O UFW continua ativo e as regras originais de isolamento QA foram restauradas. '
               'Os três comandos de encerramento retornaram rc0 e as verificações de readback estão no JSON.' if closeout['state'] == 'PASS_PRIVATE_DISTRIBUTION_CLOSED' else
               'O encerramento completo da distribuição privada ainda precisa de comprovação.'), '',
              '## Rastreabilidade', '',
              'O arquivo [fleet-rollout-summary.json](fleet-rollout-summary.json) contém os resultados por etapa, versões, hashes, timestamps, '
              'recibos E2E e SHA-256 dos arquivos de origem retidos. Não inclui comandos brutos, credenciais, configuração privada ou chaves.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--refresh', action='store_true', help='Refresh only this generator\'s existing README and summary.')
    args = parser.parse_args()
    report = Evidence(args.input_dir).build()
    out = Path(args.output_dir)
    if args.refresh:
        existing = out / 'fleet-rollout-summary.json'
        if out.is_symlink() or not out.is_dir() or existing.is_symlink() or (out / 'README.md').is_symlink():
            parser.error('Refresh requires the existing generated directory and regular output files.')
        if set(p.name for p in out.iterdir()) != {'fleet-rollout-summary.json', 'README.md'}:
            parser.error('Refresh refuses directories containing any other files.')
        if json.loads(existing.read_text()).get('schema') != 'hara.commander.private-fleet-rollout-evidence.v1':
            parser.error('Existing summary is not this generator\'s output.')
    else:
        out.mkdir(mode=0o755)
    for name, data in (('fleet-rollout-summary.json', json.dumps(report, sort_keys=True, indent=2) + '\n'),
                       ('README.md', markdown(report))):
        mode = 'w' if args.refresh else 'x'
        with (out / name).open(mode, encoding='utf-8') as stream:
            stream.write(data)
    print(json.dumps({'output_dir': str(out), 'native_pass': report['native_pass_count'],
                      'commander_e2e_pass': report['commander_device_info_pass_count'],
                      'state': report['rollout_state'], 'input_errors': report['input_errors']}, sort_keys=True))


if __name__ == '__main__':
    main()
