"""Simulated agent tools.

Each specialist agent owns a small allow-listed set of tools. The model only
PROPOSES tool use; this code EXECUTES it — that separation (model proposes,
code disposes) is the security architecture worth saying out loud. Tool
results are injected into the prompt as data, never as instructions.
"""

import re

FAKE_ACCOUNT = {"account_ref": "ACCT-1042", "balance": 87.46, "due_date": "Oct 03", "lines": 3}


def lookup_account(account_ref: str = "ACCT-1042") -> dict:
    return {**FAKE_ACCOUNT, "account_ref": account_ref, "last_payment": "$150.00 on Sep 05"}


def explain_charge(code: str) -> dict:
    codes = {
        "activation": {"amount": 35.00, "waivable_online": True},
        "late": {"amount": 7.00, "waivable_online": False},
        "upgrade": {"amount": 35.00, "waivable_online": False},
    }
    return {"code": code, **codes.get(code, {"amount": None, "waivable_online": None})}


def check_outage(zip_code: str) -> dict:
    clear = {"75024", "75039", "75201"}
    return {
        "zip": zip_code,
        "status": "clear" if zip_code in clear else "no confirmed incident",
        "open_incidents": 0,
    }


def run_speed_test(session_id: str) -> dict:
    return {"session": session_id[:8], "down_mbps": 312, "up_mbps": 24, "wired": True}


def compare_plans() -> dict:
    return {
        "Unlimited Welcome": {"price_per_line": 65, "premium_data_gb": 0},
        "Unlimited Plus": {"price_per_line": 80, "premium_data_gb": 50},
        "Unlimited Ultimate": {"price_per_line": 90, "premium_data_gb": 100},
    }


def device_diagnostics(model: str = "iPhone 15") -> dict:
    return {"device": model, "battery_health": "89%", "os": "latest", "issues": []}


def esim_status(imei: str) -> dict:
    return {"imei_last4": imei[-4:], "esim_active": True, "transfer_ready": True}


def activation_status(order_ref: str = "ORD-77881") -> dict:
    return {"order": order_ref, "stage": "SIM shipped", "port_eta_hours": 4}


TOOL_REGISTRY = {
    "billing": [
        ("lookup_account", lambda msg, ses: lookup_account()),
        ("explain_charge", lambda msg, ses: explain_charge(_detect_charge_code(msg))),
    ],
    "network": [
        ("check_outage", lambda msg, ses: check_outage(_detect_zip(msg) or "75024")),
        ("run_speed_test", lambda msg, ses: run_speed_test(ses)),
    ],
    "plans": [("compare_plans", lambda msg, ses: compare_plans())],
    "device": [("device_diagnostics", lambda msg, ses: device_diagnostics()), ("esim_status", lambda msg, ses: esim_status(_detect_imei(msg) or "0000"))],
    "onboarding": [("activation_status", lambda msg, ses: activation_status())],
    "generalist": [],
}

TOOL_TRIGGERS = {
    "lookup_account": [r"\bbill", r"\bbalance", r"\bpayment", r"\bcharge", r"\bhigh\b"],
    "explain_charge": [r"activation fee", r"late fee", r"upgrade fee", r"what is this charge"],
    "check_outage": [r"outage", r"down", r"no service", r"\b\d{5}\b", r"internet"],
    "run_speed_test": [r"slow", r"speed", r"buffering"],
    "compare_plans": [r"plan", r"upgrade", r"compare", r"cheaper", r"unlimited"],
    "device_diagnostics": [r"phone", r"device", r"turn on", r"frozen", r"battery"],
    "esim_status": [r"esim", r"imei", r"transfer"],
    "activation_status": [r"activate", r"activation", r"port", r"order"],
}


def _detect_zip(msg: str) -> str | None:
    m = re.search(r"\b(\d{5})\b", msg)
    return m.group(1) if m else None


def _detect_imei(msg: str) -> str | None:
    m = re.search(r"\b(\d{15})\b", msg)
    return m.group(1) if m else None


def _detect_charge_code(msg: str) -> str:
    m = msg.lower()
    for code in ("activation", "late", "upgrade"):
        if code in m:
            return code
    return "activation"


def run_tools(agent: str, message: str, session_id: str) -> list[dict]:
    calls = []
    for name, fn in TOOL_REGISTRY.get(agent, []):
        pats = TOOL_TRIGGERS.get(name, [])
        if any(re.search(p, message.lower()) for p in pats):
            result = fn(message, session_id)
            calls.append({"tool": name, "args": {"message_excerpt": message[:60]}, "result": result})
    return calls
