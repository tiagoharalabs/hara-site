#!/usr/bin/env python3
"""Offline, no-key/no-network regression of the Stripe TEST wizard."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stripe_test_activation_wizard as wiz


def expect_denied(action, label):
    try:
        action()
    except wiz.ActivationError:
        print(label + "=DENIED")
        return
    raise AssertionError("EXPECTED_DENIAL:" + label)


def sample_price(**updates):
    price = {
        "id": "price_TEST123456",
        "livemode": False,
        "active": True,
        "currency": "brl",
        "unit_amount": 8000,
        "recurring": {"interval": "month", "interval_count": 1, "usage_type": "licensed"},
        "product": "prod_TEST123456",
    }
    price.update(updates)
    return price


def tests():
    wiz.verify_dev_boundary()
    expect_denied(lambda: wiz.validate_test_key("sk_live_1234567890123"),
                  "STRIPE_LIVE_KEY")
    expect_denied(lambda: wiz.validate_test_key("pk_test_1234567890123"),
                  "STRIPE_PUBLIC_KEY")
    assert wiz.validate_test_key("sk_test_1234567890123") == "sk_test_1234567890123"
    for bad in (
        {"livemode": True},
        {"currency": "usd"},
        {"unit_amount": 8001},
        {"recurring": {"interval": "year", "interval_count": 1, "usage_type": "licensed"}},
    ):
        expect_denied(lambda b=bad: wiz.validate_price(sample_price(**b)),
                      "INVALID_PRICE_" + "_".join(bad))
    assert wiz.validate_price(sample_price()) == "price_TEST123456"

    requests = []
    class FakeStripe:
        def __init__(self,key):
            self.key = wiz.validate_test_key(key)

        def request(self, method, path, data=None, idempotency=None):
            requests.append((method, path, list(data or []), idempotency))
            if method == "GET" and path.startswith("/v1/prices?"):
                return {"data": []}
            if method == "POST" and path == "/v1/products":
                return {"id": "prod_TEST123456", "livemode": False}
            if method == "POST" and path == "/v1/prices":
                return sample_price()
            if method == "GET" and path.startswith("/v1/webhook_endpoints?"):
                return {"data": [], "has_more": False}
            if method == "POST" and path == "/v1/webhook_endpoints":
                return {
                    "id": "we_TEST123456", "url": wiz.WEBHOOK_URL, "livemode": False,
                    "secret": "whsec_TEST123456789012",
                }
            if method == "GET" and path.startswith("/v1/billing_portal/configurations?"):
                return {"data": [], "has_more": False}
            if method == "POST" and path == "/v1/billing_portal/configurations":
                return {
                    "id": "bpc_TEST123456", "livemode": False, "active": True,
                    "features": {
                        "invoice_history": {"enabled": True},
                        "payment_method_update": {"enabled": True},
                        "subscription_cancel": {"enabled": True},
                    },
                }
            raise AssertionError("UNEXPECTED_STRIPE_REQUEST:" + method + " " + path)

    stored = []
    counter = 0
    def fake_secret_names():
        nonlocal counter
        counter += 1
        if counter == 1:
            return set()
        return set(wiz.SECRET_NAMES)
    def fake_secret_put(name,value):
        stored.append((name,value))
        # No fake/real key is printed, even by this test.
    class FakeStdin:
        def isatty(self):
            return True

    output = io.StringIO()
    with patch.object(wiz, "StripeClient", FakeStripe), \
         patch.object(wiz, "secret_names", side_effect=fake_secret_names), \
         patch.object(wiz, "put_dev_secret", side_effect=fake_secret_put), \
         patch.object(wiz.getpass, "getpass", return_value="sk_test_1234567890123"), \
         patch.object(wiz.sys, "stdin", FakeStdin()), \
         contextlib.redirect_stdout(output):
        wiz.run(apply=True)

    assert {name for name,_ in stored} == set(wiz.SECRET_NAMES)
    assert [name for name,_ in stored][-1] == "STRIPE_SECRET_KEY", "secret API key must activate DEV LAST"
    assert stored[0] == ("STRIPE_WEBHOOK_SECRET", "whsec_TEST123456789012")
    assert stored[1] == ("STRIPE_PRICE_STANDARD", "price_TEST123456")
    assert stored[2] == ("STRIPE_PORTAL_CONFIGURATION", "bpc_TEST123456")
    assert stored[3] == ("STRIPE_SECRET_KEY", "sk_test_1234567890123")
    log = output.getvalue()
    assert "sk_test_" not in log and "whsec_" not in log
    assert "STRIPE_LIVE_KEYS_INSTALLED=FALSE" in log
    price_request = next(x for x in requests if x[1] == "/v1/prices")
    assert ("currency", "brl") in price_request[2]
    assert ("unit_amount", "8000") in price_request[2]
    assert ("recurring[interval]", "month") in price_request[2]
    webhook_request = next(x for x in requests if x[1] == "/v1/webhook_endpoints")
    assert ("url", wiz.WEBHOOK_URL) in webhook_request[2]
    assert {value for key,value in webhook_request[2] if key == "enabled_events[]"} == set(wiz.EVENTS)
    assert ("api_version", "2024-06-20") in webhook_request[2]
    portal_request = next(x for x in requests if x[1] == "/v1/billing_portal/configurations")
    assert ("features[subscription_cancel][enabled]", "true") in portal_request[2]
    assert ("features[payment_method_update][enabled]", "true") in portal_request[2]
    print("STRIPE_TEST_WIZARD_STUB_PRODUCT_PRICE=PASS")
    print("STRIPE_TEST_WIZARD_STUB_WEBHOOK_PORTAL=PASS")
    print("STRIPE_TEST_WIZARD_SECRET_ORDER_AND_REDACTION=PASS")
    print("STRIPE_TEST_WIZARD_PRODUCTION_SIDE_EFFECT=ABSENT")


if __name__ == "__main__":
    tests()
