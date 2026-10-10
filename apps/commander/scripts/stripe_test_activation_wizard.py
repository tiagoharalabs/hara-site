#!/usr/bin/env python3
"""Private, test-mode-only Stripe bootstrap for H.A.R.A. Commander.

Run interactively on Services. No secret is accepted on argv or saved to disk.
No production Stripe or Cloudflare writes. No subscription/payment is created.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
DEV_CONFIG = APP / "wrangler.dev.jsonc"
WRANGLER = ROOT / "node_modules/.bin/wrangler"
STRIPE_API = "https://api.stripe.com/v1"
WEBHOOK_URL = "https://hara-commander-dev-v2.tiago-sartori.workers.dev/api/billing/stripe/webhook"
PORTAL_RETURN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev/#plans"
LOOKUP_KEY = "hara_commander_standard_brl_8000_month_v1"
PRODUCT_NAME = "H.A.R.A. Commander Pro"
EVENTS = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
)
SECRET_NAMES = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_STANDARD",
    "STRIPE_PORTAL_CONFIGURATION",
)


class ActivationError(Exception):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise ActivationError(code)


def validate_test_key(value: str) -> str:
    key = value.strip()
    require(bool(re.fullmatch(r"sk_test_[A-Za-z0-9]{12,}", key)),
            "ONLY_STRIPE_TEST_SECRET_KEYS_ALLOWED")
    return key


def validate_price(price: dict) -> str:
    require(price.get("livemode") is False, "STRIPE_LIVE_PRICE_REJECTED")
    require(price.get("active") is True, "STRIPE_PRICE_NOT_ACTIVE")
    require(price.get("currency") == "brl" and price.get("unit_amount") == 8000,
            "STRIPE_PRICE_MUST_BE_BRL_80")
    recurring = price.get("recurring") or {}
    require(recurring.get("interval") == "month"
            and recurring.get("interval_count", 1) == 1,
            "STRIPE_PRICE_MUST_BE_MONTHLY")
    require(recurring.get("usage_type", "licensed") == "licensed", "STRIPE_PRICE_METERED_DENIED")
    value = str(price.get("id") or "")
    require(bool(re.fullmatch(r"price_[A-Za-z0-9]+", value)), "STRIPE_PRICE_ID_INVALID")
    return value


def verify_dev_boundary() -> None:
    require(WRANGLER.is_file(), "WRANGLER_NOT_INSTALLED")
    cfg = json.loads(DEV_CONFIG.read_text(encoding="utf-8"))
    require(cfg.get("name") == "hara-commander-dev-v2", "WRONG_WORKER_NAME")
    require(cfg.get("vars", {}).get("ENVIRONMENT") == "DEV", "PRODUCTION_CONFIG_REJECTED")
    require(cfg.get("vars", {}).get("STORAGE_MODE") == "REMOTE_DEV", "PRODUCTION_DB_REJECTED")
    require(cfg.get("workers_dev") is True, "DEV_DOMAIN_REQUIRED")
    require(DEV_CONFIG.resolve().is_relative_to(ROOT.resolve()), "CONFIG_OUTSIDE_REPO")


def secret_names() -> set[str]:
    proc = subprocess.run(
        [str(WRANGLER), "secret", "list", "-c", str(DEV_CONFIG)],
        cwd=ROOT, capture_output=True, text=True, timeout=45, check=False,
    )
    require(proc.returncode == 0, "CLOUDFLARE_DEV_SECRET_LIST_UNAVAILABLE")
    try:
        items = json.loads(proc.stdout)
    except (ValueError, TypeError):
        raise ActivationError("CLOUDFLARE_SECRET_LIST_RESPONSE_INVALID") from None
    require(isinstance(items, list), "CLOUDFLARE_SECRET_LIST_NOT_ARRAY")
    return {str(x["name"]) for x in items if isinstance(x, dict) and "name" in x}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ActivationError("STRIPE_REDIRECT_NOT_ALLOWED")


class StripeClient:
    def __init__(self, key: str):
        self.key = validate_test_key(key)
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method: str, path: str, data=None, idempotency: str | None = None):
        require(method in ("GET", "POST"), "STRIPE_METHOD_DENIED")
        require(path.startswith("/v1/") and not path.startswith("//"), "STRIPE_PATH_DENIED")
        headers = {"Authorization": "Bearer " + self.key, "Accept": "application/json"}
        if idempotency:
            require(method == "POST", "IDEMPOTENCY_METHOD_INVALID")
            headers["Idempotency-Key"] = idempotency
        payload = None
        if method == "POST":
            payload = urllib.parse.urlencode(data or [], doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request("https://api.stripe.com" + path,
                                         data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                require(200 <= response.status < 300, "STRIPE_NON_2XX_RESPONSE")
                body = response.read(256 * 1024)
            result = json.loads(body)
        except urllib.error.HTTPError as exc:
            raise ActivationError("STRIPE_API_HTTP_" + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ActivationError("STRIPE_API_UNREACHABLE") from None
        except (ValueError, TypeError):
            raise ActivationError("STRIPE_API_INVALID_JSON") from None
        require(isinstance(result, dict), "STRIPE_API_NOT_OBJECT")
        return result


def ensure_price(client: StripeClient) -> tuple[str, str]:
    query = urllib.parse.urlencode({"lookup_keys[]": LOOKUP_KEY, "limit": "10"})
    existing = client.request("GET", "/v1/prices?" + query).get("data", [])
    require(isinstance(existing, list) and len(existing) <= 1, "STRIPE_DUPLICATE_PRICE_LOOKUP")
    if existing:
        price = existing[0]
        price_id = validate_price(price)
        product_id = str(price.get("product") or "")
        require(product_id.startswith("prod_"), "STRIPE_PRODUCT_ID_INVALID")
        product = client.request("GET", "/v1/products/" + product_id)
        require(product.get("livemode") is False and product.get("name") == PRODUCT_NAME,
                "STRIPE_PRICE_PRODUCT_MISMATCH")
        return product_id, price_id

    product = client.request(
        "POST", "/v1/products",
        [("name", PRODUCT_NAME),
         ("description", "Assinatura mensal para execucao governada no ChatGPT"),
         ("metadata[product]", "HARA_COMMANDER"),
         ("metadata[plan_code]", "STANDARD")],
        "hara-commander-test-standard-product-v1",
    )
    require(product.get("livemode") is False, "STRIPE_LIVE_PRODUCT_REJECTED")
    product_id = str(product.get("id") or "")
    require(bool(re.fullmatch(r"prod_[A-Za-z0-9]+", product_id)), "STRIPE_PRODUCT_ID_INVALID")
    price = client.request(
        "POST", "/v1/prices",
        [("product", product_id), ("currency", "brl"), ("unit_amount", "8000"),
         ("recurring[interval]", "month"), ("recurring[interval_count]", "1"),
         ("recurring[usage_type]", "licensed"), ("lookup_key", LOOKUP_KEY),
         ("nickname", "Commander Pro R$80 por mes"),
         ("metadata[plan_code]", "STANDARD")],
        "hara-commander-test-standard-price-v1",
    )
    return product_id, validate_price(price)


def ensure_webhook(client: StripeClient) -> tuple[str, str]:
    result = client.request("GET", "/v1/webhook_endpoints?limit=100")
    require(result.get("has_more") is False, "WEBHOOK_LIST_PAGINATION_REVIEW_REQUIRED")
    endpoints = [x for x in result.get("data", [])
                 if isinstance(x, dict) and x.get("url") == WEBHOOK_URL]
    require(len(endpoints) <= 1, "WEBHOOK_DUPLICATE_ENDPOINT_REVIEW_REQUIRED")
    if endpoints:
        endpoint = endpoints[0]
        require(endpoint.get("livemode") is False, "LIVE_WEBHOOK_REJECTED")
        require(endpoint.get("status") == "enabled", "WEBHOOK_DISABLED")
        require(set(EVENTS).issubset(set(endpoint.get("enabled_events") or [])),
                "WEBHOOK_REQUIRED_EVENTS_MISSING")
        secret = getpass.getpass("Webhook existente: cole o whsec_ de TESTE (oculto): ").strip()
    else:
        params = [("url", WEBHOOK_URL),
                  ("description", "HARA Commander DEV - Stripe test only"),
                  ("api_version", "2024-06-20")]
        params += [("enabled_events[]", event) for event in EVENTS]
        endpoint = client.request("POST", "/v1/webhook_endpoints", params,
                                  "hara-commander-test-webhook-v1")
        require(endpoint.get("livemode") is False
                and endpoint.get("url") == WEBHOOK_URL, "STRIPE_WEBHOOK_WRONG_DESTINATION")
        secret = str(endpoint.get("secret") or "")
    require(bool(re.fullmatch(r"whsec_[A-Za-z0-9]+", secret)),
            "STRIPE_WEBHOOK_SIGNING_SECRET_INVALID")
    endpoint_id = str(endpoint.get("id") or "")
    require(bool(re.fullmatch(r"we_[A-Za-z0-9]+", endpoint_id)), "WEBHOOK_ID_INVALID")
    return endpoint_id, secret


def ensure_portal(client: StripeClient) -> str:
    result = client.request("GET", "/v1/billing_portal/configurations?limit=100")
    require(result.get("has_more") is False, "PORTAL_LIST_PAGINATION_REVIEW_REQUIRED")
    existing = [x for x in result.get("data", []) if isinstance(x, dict)
                and x.get("metadata", {}).get("source") == "HARA_COMMANDER_TEST_WIZARD"]
    require(len(existing) <= 1, "PORTAL_MULTIPLE_CONFIG_REVIEW_REQUIRED")
    if existing:
        configuration = existing[0]
    else:
        configuration = client.request("POST", "/v1/billing_portal/configurations",
            [("features[invoice_history][enabled]", "true"),
             ("features[payment_method_update][enabled]", "true"),
             ("features[subscription_cancel][enabled]", "true"),
             ("features[subscription_cancel][mode]", "at_period_end"),
             ("features[subscription_update][enabled]", "false"),
             ("default_return_url", PORTAL_RETURN),
             ("metadata[source]", "HARA_COMMANDER_TEST_WIZARD")],
            "hara-commander-test-portal-v1")
    require(configuration.get("livemode") is False and configuration.get("active") is True,
            "PORTAL_CONFIGURATION_NOT_ACTIVE_TEST")
    features = configuration.get("features") or {}
    for feature in ("invoice_history", "payment_method_update", "subscription_cancel"):
        require(features.get(feature, {}).get("enabled") is True,
                "PORTAL_FEATURE_REQUIRED_" + feature.upper())
    config_id = str(configuration.get("id") or "")
    require(bool(re.fullmatch(r"bpc_[A-Za-z0-9]+", config_id)), "PORTAL_ID_INVALID")
    return config_id


def put_dev_secret(name: str, value: str) -> None:
    require(name in SECRET_NAMES, "SECRET_NAME_NOT_APPROVED")
    require(value and "\n" not in value and "\r" not in value, "SECRET_FORMAT_REJECTED")
    environment = dict(os.environ, CI="1")
    result = subprocess.run(
        [str(WRANGLER), "secret", "put", name, "-c", str(DEV_CONFIG)],
        input=value + "\n", text=True, capture_output=True,
        cwd=ROOT, env=environment, check=False, timeout=95,
    )
    require(result.returncode == 0, "CLOUDFLARE_DEV_SECRET_PUT_FAILED_" + name)
    print(name + "=INSTALLED_DEV")


def run(*, apply: bool) -> None:
    verify_dev_boundary()
    existing = secret_names()
    print("STRIPE_ACTIVATION_BOUNDARY=TEST_ONLY")
    print("CLOUDFLARE_WORKER=hara-commander-dev-v2")
    print("CHARGE_REAL_CUSTOMER=FALSE")
    for name in SECRET_NAMES:
        print(name + ("=PRESENT" if name in existing else "=MISSING"))
    if not apply:
        print("STRIPE_TEST_ACTIVATION_PLAN=READY_FOR_INTERACTIVE_APPLY")
        return
    require(sys.stdin.isatty(), "INTERACTIVE_PRIVATE_TERMINAL_REQUIRED")
    require(not (set(SECRET_NAMES) & existing), "DEV_STRIPE_SECRETS_ALREADY_EXIST_REVIEW_REQUIRED")
    key = validate_test_key(
        getpass.getpass("Cole a chave secreta Stripe de TESTE (sk_test_, oculta): ")
    )
    client = StripeClient(key)
    product_id, price_id = ensure_price(client)
    webhook_id, signing_secret = ensure_webhook(client)
    portal_id = ensure_portal(client)
    # Do not log the API key, webhook signing secret, authorization headers,
    # Stripe API response bodies, or Cloudflare secret-put process output.
    print("STRIPE_TEST_PRODUCT=" + product_id)
    print("STRIPE_TEST_PRICE_VALID_BRL80_MONTH=" + price_id)
    print("STRIPE_TEST_WEBHOOK_CREATED_OR_REUSED=" + webhook_id)
    print("STRIPE_TEST_PORTAL_CONFIGURATION=" + portal_id)
    print("STRIPE_TEST_OBJECTS_VALIDATED=PASS")
    put_dev_secret("STRIPE_WEBHOOK_SECRET", signing_secret)
    put_dev_secret("STRIPE_PRICE_STANDARD", price_id)
    put_dev_secret("STRIPE_PORTAL_CONFIGURATION", portal_id)
    # Secret key LAST; DEV checkout becomes available only after earlier config.
    put_dev_secret("STRIPE_SECRET_KEY", key)
    refreshed = secret_names()
    require(set(SECRET_NAMES).issubset(refreshed), "DEV_SECRET_READBACK_INCOMPLETE")
    print("STRIPE_TEST_DEV_FOUR_SECRETS=PASS")
    print("STRIPE_LIVE_KEYS_INSTALLED=FALSE")
    print("STRIPE_TEST_PAYMENT_EXECUTED=FALSE")
    print("STRIPE_TEST_NEXT_GATE=HOSTED_CHECKOUT_AND_WEBHOOK")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Safe, no changes (default)")
    group.add_argument("--apply", action="store_true", help="Test Stripe objects + DEV secrets only")
    args = parser.parse_args()
    try:
        run(apply=args.apply)
    except (ActivationError, subprocess.TimeoutExpired) as exc:
        print("STRIPE_TEST_ACTIVATION=" + (
            str(exc) if isinstance(exc, ActivationError) else "OPERATION_TIMEOUT"
        ))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
