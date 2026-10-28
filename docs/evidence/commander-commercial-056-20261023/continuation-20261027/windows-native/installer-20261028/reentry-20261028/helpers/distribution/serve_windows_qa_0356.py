#!/usr/bin/python3.10
"""Temporary internal HTTPS distribution of the exact eight signed .56 files to the current Windows QA address.

No API, directory listing, redirects, uploads, or filesystem reads after start.
The product origin remains separate from this private release URL.
"""
import argparse
import ctypes
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import resource
import selectors
import ssl
import time

FILES = {
    'agent/linux.py': 'ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d',
    'agent/windows.ps1': 'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620',
    'install/linux.sh': 'a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f',
    'install/windows.ps1': '2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401',
    'release/agent-manifest.json': 'fd8fef20c54fd805d8837a665334ac5c075289545b5d66b7fbaac1954a16f56a',
    'release/agent-manifest.sig.json': 'b76fff632e0f7771acc49c9f10f2085b2789133dc5d242a7e3fcb89652e37743',
    'release/release-signing-public.jwk': '4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b',
}
SUMS = ''.join(f'{digest}  {name}\n' for name, digest in list(FILES.items())[:4]).encode()
FILES['release/SHA256SUMS'] = hashlib.sha256(SUMS).hexdigest()
PREFIX = '/releases/0.3.56/'
NETWORKS = tuple(ipaddress.ip_network(n) for n in ('192.168.252.113/32',))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--tls-cert', type=Path, required=True)
    parser.add_argument('--tls-key', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT_LAUNCHER')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    blobs = {}
    for name, expected in FILES.items():
        path = args.assets / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2097152:
            raise SystemExit('ASSET_FILE_INVALID')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit('ASSET_PIN_MISMATCH')
        blobs[PREFIX + name] = data
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(args.tls_cert), str(args.tls_key))
    certificate_sha = hashlib.sha256(ssl.PEM_cert_to_DER_cert(args.tls_cert.read_text())).hexdigest()
    counts = {'served': 0, 'denied': 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'HARA-Private-QA/1'
        sys_version = ''

        def do_GET(self):
            address = ipaddress.ip_address(self.client_address[0])
            data = blobs.get(self.path)
            if not any(address in network for network in NETWORKS) or data is None:
                counts['denied'] += 1
                self.send_error(404)
                return
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
            connection.settimeout(10)
            try:
                return context.wrap_socket(connection, server_side=True), address
            except BaseException:
                connection.close()
                raise

        def handle_error(self, *_args):
            counts['denied'] += 1

    servers = []
    selector = selectors.DefaultSelector()
    try:
        for address in ('192.168.10.23',):
            server = Server((address, 18443), Handler)
            server.timeout = 1
            servers.append(server)
            selector.register(server, selectors.EVENT_READ)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'no_new_privileges')
        deadline = time.monotonic() + 10800
        print(json.dumps({'state': 'PRIVATE_HTTPS_READY', 'pid': os.getpid(),
                          'uid': os.getuid(), 'binds': [list(s.server_address) for s in servers],
                          'files': len(blobs), 'lifetime_s': 10800,
                          'certificate_der_sha256': certificate_sha}), flush=True)
        while time.monotonic() < deadline:
            for event, _mask in selector.select(timeout=1):
                event.fileobj.handle_request()
    finally:
        for server in servers:
            server.server_close()
        selector.close()
        print(json.dumps({'state': 'PRIVATE_HTTPS_STOPPED', **counts}), flush=True)


if __name__ == '__main__':
    main()
