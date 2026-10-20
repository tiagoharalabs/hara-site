# R7 QA: no real processes/fleet changes

Copy peer_concurrent_sessions.py into a new empty directory alongside a source/ created by git archive of the chosen Commander commit. The script uses temporary HOME and a fake pty.fork with a 2-thread barrier. Exit 2 means concurrent overflow reproduced; it is NOT a successful acceptance test or proof the current remote path is concurrent. Source QA version 56a1175 and repeated against 73c3dd25. Three preexisting regressions pass as recorded in r7-independent-tests.json.
