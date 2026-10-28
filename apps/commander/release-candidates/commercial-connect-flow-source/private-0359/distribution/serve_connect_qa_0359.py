#!/usr/bin/python3.10
"""Bounded HTTPS distribution of eight pinned .59 files to two QA VM addresses.

No API, listing, redirects, uploads, or filesystem reads after initialization.
The product origin stays separate. The existing TLS files are loaded, not changed.
"""
import argparse
import ctypes
import datetime as dt
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import ssl
import stat
import time

ROOT = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028/connect-flow-20261028/private-0359')
TLS = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028/distribution-r3/tls')
HARD_DEADLINE = dt.datetime(2026, 10, 28, 19, 35, 0, tzinfo=dt.timezone.utc)
MAX_SECONDS = 2700
TLS_PEM_SHA256 = 'c15308e100ba014d463b20cc56568e2183c4c50e2b2b672af38a0926d1c879c1'
TLS_DER_SHA256 = '893aeec40a123d5fd74fd312fa1ed90e4c9881e10a562cdc126026c3d848f29e'
FILES = {
    'agent/linux.py': 'df8b2d09c5447f8d405200538a841e669a8f165e9043701d6c8efcbfe5a34d38',
    'agent/windows.ps1': 'd3a4173829186e2488c2b686f5ac3ecca62c896387f55dcdfdbcdd155253ae24',
    'install/linux.sh': '80732c941725e06f317ef42e878a0498d30f28bf890dd07d9a0b6a90f0cd0581',
    'install/windows.ps1': '2f734ab8066b46cb82fc4fc9fb25244472bc829c16043cfe5f2771ae4e6d04b4',
    'release/agent-manifest.json': 'efe39839596883875358cfc27cd7ec62c0d38acc3c03708df56034a82d35d7b4',
    'release/agent-manifest.sig.json': '888f8674ae48e511eac9b4cc8ec1858110576af6970a6e6a7db19b585ef15ba3',
    'release/release-signing-public.jwk': '4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b',
}
SUMS = ''.join(f'{digest}  {name}\n' for name, digest in list(FILES.items())[:4]).encode()
FILES['release/SHA256SUMS'] = hashlib.sha256(SUMS).hexdigest()
PREFIX = '/releases/0.3.59/'
ADDRESSES = ('192.168.252.113', '192.168.252.130')
NETWORKS = tuple(ipaddress.ip_network(address + '/32') for address in ADDRESSES)


def read_regular(path, limit, private=False):
    for parent in path.parents:
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise RuntimeError('INPUT_PARENT_NOT_DIRECTORY_OR_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise RuntimeError('INPUT_FILE_INVALID')
        if private and (before.st_uid != 0 or stat.S_IMODE(before.st_mode) != 0o600):
            raise RuntimeError('TLS_PRIVATE_KEY_CUSTODY_INVALID')
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(fd)
        leaf = path.lstat()
        identify = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns, x.st_mode, x.st_uid)
        if len(raw) != before.st_size or identify(before) != identify(after) or identify(before) != identify(leaf):
            raise RuntimeError('INPUT_CHANGED_DURING_READ')
        return raw
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--tls-cert', type=Path, required=True)
    parser.add_argument('--tls-key', type=Path, required=True)
    parser.add_argument('--expires-utc', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT_LAUNCHER')
    if (args.assets != ROOT / 'signed' or args.tls_cert != TLS / 'qa-server.crt' or
            args.tls_key != TLS / 'qa-server.key'):
        raise SystemExit('FIXED_DISTRIBUTION_PATHS_REQUIRED')
    expires = dt.datetime.fromisoformat(args.expires_utc)
    if expires.tzinfo is None or expires > HARD_DEADLINE:
        raise SystemExit('DISTRIBUTION_DEADLINE_INVALID')
    seconds = min(MAX_SECONDS, (expires - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if seconds <= 0:
        raise SystemExit('DISTRIBUTION_WINDOW_EXPIRED')
    monotonic_deadline = time.monotonic() + seconds
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Interrupt even a client stalled inside TLS/header I/O at the fixed expiry.
    # Process exit closes every socket and the unit's ExecStopPost owns cleanup.
    def expire(_signal, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    blobs = {}
    for name, expected in FILES.items():
        data = read_regular(args.assets / name, 2097152)
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit('ASSET_PIN_MISMATCH')
        blobs[PREFIX + name] = data
    certificate = read_regular(args.tls_cert, 65536)
    if hashlib.sha256(certificate).hexdigest() != TLS_PEM_SHA256:
        raise SystemExit('EXISTING_TLS_CERTIFICATE_PIN_MISMATCH')
    certificate_sha = hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.decode('ascii'))).hexdigest()
    if certificate_sha != TLS_DER_SHA256:
        raise SystemExit('EXISTING_TLS_DER_PIN_MISMATCH')
    # Metadata only: private bytes are loaded solely by the TLS implementation.
    for parent in args.tls_key.parents:
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise SystemExit('TLS_PRIVATE_KEY_PARENT_INVALID')
    key_stat = args.tls_key.lstat()
    if (not stat.S_ISREG(key_stat.st_mode) or key_stat.st_uid != 0 or
            stat.S_IMODE(key_stat.st_mode) != 0o600 or key_stat.st_nlink != 1 or
            not 0 < key_stat.st_size <= 65536):
        raise SystemExit('TLS_PRIVATE_KEY_CUSTODY_INVALID')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(args.tls_cert), str(args.tls_key))
    counts = {'served': 0, 'denied': 0}

    def remaining():
        return min(monotonic_deadline - time.monotonic(),
                   (expires - dt.datetime.now(dt.timezone.utc)).total_seconds())

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'HARA-Private-QA/1'
        sys_version = ''

        def do_GET(self):
            address = ipaddress.ip_address(self.client_address[0])
            data = blobs.get(self.path)
            if remaining() <= 0:
                self.close_connection = True
                return
            if not any(address in network for network in NETWORKS) or data is None:
                counts['denied'] += 1
                self.send_error(404)
                return
            self.connection.settimeout(max(0.001, min(10, remaining())))
            counts['served'] += 1
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    class Server(http.server.HTTPServer):
        allow_reuse_address = False

        def get_request(self):
            connection, address = self.socket.accept()
            try:
                ip = ipaddress.ip_address(address[0])
                if remaining() <= 0 or not any(ip in network for network in NETWORKS):
                    raise OSError('QA_CLIENT_OR_WINDOW_REFUSED')
                connection.settimeout(max(0.001, min(10, remaining())))
                return context.wrap_socket(connection, server_side=True), address
            except BaseException:
                connection.close()
                raise

        def handle_error(self, *_args):
            counts['denied'] += 1

    server = None
    selector = selectors.DefaultSelector()
    try:
        if remaining() <= 0:
            raise SystemExit('DISTRIBUTION_WINDOW_EXPIRED')
        server = Server(('192.168.10.23', 18446), Handler)
        server.timeout = 1
        selector.register(server, selectors.EVENT_READ)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'no_new_privileges')
        print(json.dumps({'state': 'PRIVATE_HTTPS_READY', 'pid': os.getpid(),
                          'uid': os.getuid(), 'bind': list(server.server_address),
                          'allowed_sources': list(ADDRESSES), 'files': len(blobs),
                          'lifetime_max_s': MAX_SECONDS, 'expires_at_utc': expires.isoformat(),
                          'hard_deadline_utc': HARD_DEADLINE.isoformat(),
                          'certificate_der_sha256': certificate_sha}), flush=True)
        while remaining() > 0:
            for event, _mask in selector.select(timeout=max(0, min(1, remaining()))):
                if remaining() > 0:
                    event.fileobj.handle_request()
    finally:
        if server is not None:
            server.server_close()
        selector.close()
        print(json.dumps({'state': 'PRIVATE_HTTPS_STOPPED', **counts}), flush=True)


if __name__ == '__main__':
    main()
