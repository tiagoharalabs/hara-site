# R21 — Observer and Storage first actual commercial installs

Independent HARA Commander checks on 21 October 2026 after owner provided an Observer installer session transcript. Both devices use commercial 0.3.43 with unique enrollments, ASK_EVERY_ACTION and OUTBOUND_RELAY; MCP ping and file reads work and local service is active/enabled with 0600 config. The current public 0.3.43 distribution now passes the live cryptographic integrity gate and two-host CDN hash consistency.

IMPORTANT: public manifest SHA 53c0cbc2... is NOT R19 reviewed signed manifest SHA 2ec2b3cc...; 3 of 4 asset hashes differ from that reviewed release although both show 0.3.43. Do not conflate signature validity, version label and reviewed build provenance. No evidence of compromise or unsafe installation is asserted. No deployment, restart, token/secret read or installed-Agent mutation in this review.

See docs/operations/HARA_COMMANDER_OBSERVER_STORAGE_R21_20261021.md. observational JSON contains only sanitized hashes and states, not credentials.
