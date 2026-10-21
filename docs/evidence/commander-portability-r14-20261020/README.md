# R14 HARA Commander: portability tests on real operating systems

Storage: Fedora 43 x86_64 Python 3.14.4. Observer: Ubuntu 22.04 aarch64 Python 3.10.12. Each ran 6 R11 signed-preflight cases and 6 R13 enrollment-ACK error cases using only 127.0.0.1, a disposable test key and ephemeral HOME; both suites exit 0 on each host. This is NOT a real install, cloud enrollment, or production signature. The 13-file QA input tar SHA-256 is in qa-source-manifest.json. No client secrets or private keys were read. See docs/operations/HARA_COMMANDER_INSTALL_READINESS_R14_20261020.md.
