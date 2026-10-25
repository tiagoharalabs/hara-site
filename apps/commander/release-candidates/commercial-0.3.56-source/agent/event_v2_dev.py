"""DEV-only wake driver for the adjacent commercial 0.3.56 Agent.

No tool, quota, journal, credential store or installed Agent is imported here.
The existing guardian owns this heartbeat process and the durable executor.
These review sources are not a signed/installable release.
"""
import importlib.util
import random
import select
import socket
import struct
import sys
import time
from pathlib import Path

PROBE = 'HARA_EVENT_V2_PROBE_V1'
ACK = 'HARA_EVENT_V2_PROBE_ACK_V1'


class WakeGate:
    """A coalesced hint, never execution authority. Survives worker replacement."""
    def __init__(self, semaphore, max_drain=8):
        if type(max_drain) is not int or not 1 <= max_drain <= 8:
            raise ValueError('EVENT_V2_DRAIN_BOUND_INVALID')
        self.signal = semaphore
        self.limit = max_drain
        self.remaining = max_drain  # one bounded startup reconciliation

    def notify(self):
        try:
            self.signal.release()
        except ValueError:
            pass  # already signaled; call identities stay in durable truth

    def wait(self, timeout=0.5):
        if self.remaining:
            return True
        if not self.signal.acquire(timeout=timeout):
            return False
        self.remaining = self.limit
        return True

    def after_claim(self, has_call):
        self.remaining = max(0, self.remaining - 1) if has_call else 0
        if has_call and not self.remaining:
            self.notify()  # yield between batches, without stranding backlog
            time.sleep(0.1)
        # Never drain/reset the signal on an empty response: a concurrent wake
        # may have arrived after the server observed the queue as empty.


class ProbeState:
    def __init__(self, now):
        self.next_at = now
        self.deadline = None

    def due(self, now):
        return self.deadline is None and now >= self.next_at

    def sent(self, now):
        self.deadline = now + 20.0
        self.next_at = now + 60.0

    def confirm(self, text, now):
        if text != ACK or self.deadline is None or now >= self.deadline:
            return False
        self.deadline = None
        return True

    def check(self, now):
        if self.deadline is not None and now >= self.deadline:
            raise RuntimeError('EVENT_V2_PROBE_TIMEOUT')


def progress_sleep(seconds, progress, *, sleep=time.sleep, monotonic=time.monotonic):
    until = monotonic() + seconds
    while monotonic() < until:
        delay = min(15.0, until - monotonic())
        progress('HEARTBEAT_RETRY', delay=delay, code='EVENT_V2_RECONNECT_WAIT')
        sleep(delay)


def is_durable_wake(event):
    return event.get('type') == 'CALL_AVAILABLE'


def load_wire():
    path = Path(__file__).with_name('event_v2_wire.py')
    spec = importlib.util.spec_from_file_location('hara_commercial_0356_event_v2_wire', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('EVENT_V2_WIRE_REQUIRED')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_session(agent, config, gate, wire, *, liveness_state, monotonic=time.monotonic):
    agent._relay_progress('HEARTBEAT_ATTEMPT')
    sock = wire.open_event_socket(config['HARA_COMMANDER_URL'], config['HARA_DEVICE_TOKEN'])
    agent._relay_progress('HEARTBEAT_ATTEMPT')
    probe = ProbeState(monotonic())
    confirmed = False
    try:
        while True:
            now = monotonic()
            probe.check(now)
            if probe.due(now):
                sock.settimeout(20.0)
                wire.send_text(sock, PROBE)
                probe.sent(monotonic())
            # Progress proves only responsiveness. Only a fresh authenticated
            # probe ACK below proves network recovery to the #322 guardian.
            agent._relay_progress('HEARTBEAT_ATTEMPT')
            if now - liveness_state['at'] >= wire.DURABLE_LIVENESS_SECONDS:
                wire.send_liveness(sock)
                liveness_state['at'] = monotonic()
                agent._relay_progress('HEARTBEAT_ATTEMPT')
            buffered = sock.pending() or bool(wire._UPGRADE_REMAINDER.get(sock))
            if not buffered and not select.select([sock], [], [], 0.5)[0]:
                continue
            deadline = min(monotonic() + 25.0, probe.deadline or float('inf'))
            frame = wire.recv_server_frame(sock, deadline=deadline)
            if frame.opcode == 8:
                code = struct.unpack('!H', frame.payload[:2])[0] if len(frame.payload) >= 2 else 1000
                raise RuntimeError('EVENT_V2_AUTHORIZATION_ENDED' if code == 4003 else 'EVENT_V2_SERVER_CLOSED')
            if frame.opcode == 9:
                agent._relay_progress('HEARTBEAT_ATTEMPT')
                wire.send_pong(sock, frame.payload)
                continue
            if frame.opcode == 10:
                continue  # protocol PONG is not application health
            text = frame.payload.decode('utf-8')
            if text == ACK:
                if not probe.confirm(text, monotonic()):
                    raise RuntimeError('EVENT_V2_UNSOLICITED_PROBE_ACK')
                agent._relay_progress('HEARTBEAT_CONFIRMED')
                agent.try_write_runtime_status(heartbeat_at=agent.utcnow(),
                                              error_code=None, error_at=None)
                if not confirmed:
                    gate.notify()  # reconcile notifications lost while offline
                    confirmed = True
                continue
            event = wire.parse_event_frame(frame)
            if not is_durable_wake(event):
                raise RuntimeError('EVENT_V2_TRANSIENT_NOT_ADMITTED')
            gate.notify()
    finally:
        # A failed peer cannot delay guardian progress for another full send
        # timeout during a graceful close. This disposable worker aborts TLS.
        wire._PENDING_PONG.pop(sock, None)
        wire._UPGRADE_REMAINDER.pop(sock, None)
        sock.close()


def heartbeat_worker(agent, config):
    if not agent.event_v2_dev_enabled(config):
        raise RuntimeError('EVENT_V2_DEV_REQUIRED')
    gate = WakeGate(config['_event_v2_wake_signal'])
    wire = load_wire()
    policy = wire.ReconnectPolicy()
    entropy = random.SystemRandom()
    liveness_state = {'at': time.monotonic()}
    progress_sleep(policy.startup_delay(entropy.random()), agent._relay_progress)
    attempt = 0
    while True:
        started = time.monotonic()
        try:
            run_session(agent, config, gate, wire, liveness_state=liveness_state)
        except Exception as exc:
            code = agent.safe_error_code(exc)
            if code in {'EVENT_V2_AUTHORIZATION_ENDED', 'EVENT_V2_AUTH_REJECTED'}:
                agent._relay_progress('REVOKED', code=code)
                return
            if code == 'EVENT_V2_DEV_NOT_ADMITTED':
                # Deliberately stop this mode, with no downgrade to V1.
                agent._relay_progress('REVOKED', code=code)
                return
            if time.monotonic() - started >= 60:
                attempt = 0
            delay = policy.delay(attempt, entropy.random())
            attempt = min(attempt + 1, 31)
            agent._relay_progress('HEARTBEAT_RETRY', delay=min(delay, 15), code=code)
            progress_sleep(delay, agent._relay_progress)
