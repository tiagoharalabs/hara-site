#!/usr/bin/env python3
"""Offline proof of manual-only commercial onboarding on both platforms.

Mock local systemctl and TTY only: this file NEVER starts or stops a real
customer Agent, alters systemd, registers a Windows task, or accesses Cloudflare.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[1]
LINUX_INSTALL = (APP / "public/install/linux.sh").read_text(encoding="utf-8")
WINDOWS_INSTALL = (APP / "public/install/windows.ps1").read_text(encoding="utf-8")
WINDOWS_AGENT = (APP / "public/agent/windows.ps1").read_text(encoding="utf-8")
LINUX_AGENT_FILE = APP / "public/agent/linux.py"
ns = {"__name__": "hara_manual_agent_policy_offline", "__file__": str(LINUX_AGENT_FILE)}
exec(compile(LINUX_AGENT_FILE.read_text(encoding="utf-8"), str(LINUX_AGENT_FILE), "exec"), ns)


def need(test: bool, name: str):
    assert test, "MANUAL_AGENT_POLICY_" + name + "_FAILED"
    print("MANUAL_AGENT_POLICY_" + name + "=PASS")


need('systemctl --user start "$SERVICE"' in LINUX_INSTALL, "LINUX_INSTALL_START_ONCE")
need('systemctl --user enable --now hara-commander-agent.service' not in LINUX_INSTALL,
     "LINUX_NO_AUTOSTART")
need('systemctl --user disable "$SERVICE"' in LINUX_INSTALL, "LINUX_FORCE_DEFAULT_DISABLED")
need("Restart=on-failure" in LINUX_INSTALL, "LINUX_FAILED_SESSION_BACKOFF")
need('if [ "$UPDATE_SERVICE_WAS_ACTIVE" = TRUE ]; then' in LINUX_INSTALL,
     "LINUX_UPDATE_PRESERVES_STOPPED")
need('if [ "$REENROLL_SERVICE_WAS_ACTIVE" != TRUE ]; then' in LINUX_INSTALL,
     "LINUX_REENROLL_PRESERVES_STOPPED")
need('mode="ASK_EVERY_ACTION"' in LINUX_INSTALL, "LINUX_MUTATION_DEFAULT_ASK")

need("New-ScheduledTaskTrigger -AtLogOn" not in WINDOWS_INSTALL, "WINDOWS_NO_LOGON_TRIGGER")
need("New-ScheduledTaskTrigger -AtStartup" not in WINDOWS_INSTALL, "WINDOWS_NO_STARTUP_TRIGGER")
need("Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Settings $Settings" in WINDOWS_INSTALL,
     "WINDOWS_ON_DEMAND_TASK")
need("$Registered.Triggers" in WINDOWS_INSTALL, "WINDOWS_TRIGGER_READBACK_FAIL_CLOSED")
need("$UpdateTaskWasRunning" in WINDOWS_INSTALL, "WINDOWS_UPDATE_PRESERVES_STOPPED")
need('else { "ASK_EVERY_ACTION" }' in WINDOWS_INSTALL, "WINDOWS_MUTATION_DEFAULT_ASK")
need("function Start-ManualOperatorConsole" in WINDOWS_AGENT, "WINDOWS_MANUAL_ENTRYPOINT")
need('Start-ScheduledTask -TaskName $AgentTaskName' in WINDOWS_AGENT,
     "WINDOWS_MANUAL_TASK_START")
need('$startedHere -and $currentTask -and -not $currentTask.Triggers' in WINDOWS_AGENT,
     "WINDOWS_MANUAL_EXIT_CLEANUP")
need("Stop-ScheduledTask -TaskName $AgentTaskName" in WINDOWS_AGENT,
     "WINDOWS_EXPLICIT_STOP")


def probe(*, already_active: bool, enabled: bool, failure: bool = False):
    calls = []

    def fake_systemctl(action):
        calls.append(action)
        if action == "is-active":
            return already_active
        if action == "is-enabled":
            return enabled
        return True

    def fake_console():
        calls.append("console")
        if failure:
            raise RuntimeError("FAKE_LOCAL_CONSOLE_FAILURE")

    ns["_manual_agent_systemctl"] = fake_systemctl
    ns["start_operator_console"] = fake_console
    ns["sys"] = SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    try:
        ns["start_manual_operator_console"]()
        need(not failure, "EXPECTED_CONSOLE_EXCEPTION")
    except RuntimeError as exc:
        need(failure and str(exc) == "FAKE_LOCAL_CONSOLE_FAILURE",
             "CONSOLE_ERROR_NOT_SUPPRESSED")
    return calls


need(probe(already_active=False, enabled=False) ==
     ["is-active", "start", "console", "is-enabled", "stop"],
     "LINUX_MANUAL_CONNECT_THEN_DISCONNECT")
need(probe(already_active=False, enabled=True) ==
     ["is-active", "start", "console", "is-enabled"],
     "LINUX_EXPLICIT_PERSISTENCE_RESPECTED")
need(probe(already_active=True, enabled=False) == ["is-active", "console"],
     "LINUX_EXISTING_DAEMON_NOT_STOPPED")
need(probe(already_active=False, enabled=False, failure=True) ==
     ["is-active", "start", "console", "is-enabled", "stop"],
     "LINUX_CONSOLE_FAILURE_CLEANUP")

ns["sys"] = SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False))
ns["_manual_agent_systemctl"] = lambda action: (_ for _ in ()).throw(
    AssertionError("SERVICE_SIDE_EFFECT_WITHOUT_TTY"))
try:
    ns["start_manual_operator_console"]()
except RuntimeError as exc:
    need(str(exc) == "LOCAL_OPERATOR_TERMINAL_REQUIRED",
         "LINUX_NONINTERACTIVE_CALL_DENIED")
else:
    raise AssertionError("LOCAL_OPERATOR_TTY_REQUIREMENT_BYPASSED")

try:
    ns["_manual_agent_systemctl"] = ns.get("_manual_agent_systemctl_original", None)
    # Exercise the real fixed-action guard, without executing systemctl.
    secure = {}
    exec(compile(LINUX_AGENT_FILE.read_text(encoding="utf-8"),
                 str(LINUX_AGENT_FILE),"exec"),secure)
    secure["_manual_agent_systemctl"]("delete")
except ValueError as exc:
    need(str(exc) == "AGENT_SERVICE_ACTION_DENIED", "SERVICE_VERB_ALLOWLIST")
else:
    raise AssertionError("AGENT_SERVICE_VERB_ALLOWLIST_BYPASSED")

print("MANUAL_AGENT_POLICY_PROD_DEVICE_MUTATIONS=FALSE")
print("MANUAL_AGENT_POLICY_WINDOWS_RUNTIME_PROOF=PENDING_REAL_WINDOWS_HOST")
