import pytest


def test_nowpayments_verify_webhook_raw():
    from integrations.payments.nowpayments import NowPaymentsGateway

    gw = NowPaymentsGateway(api_key="x", ipn_secret="secret")
    raw = b'{"a":1}'
    import hmac, hashlib

    sig = hmac.new(b"secret", raw, hashlib.sha512).hexdigest()
    assert gw.verify_webhook_raw(raw_body=raw, signature=sig) is True


@pytest.mark.asyncio
async def test_nowpayments_create_payment_calls_api(monkeypatch):
    from integrations.payments.nowpayments import NowPaymentsGateway

    class DummyResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class DummyClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, *, method, url, headers, json):
            assert method == "POST"
            assert url.endswith("/v1/payment")
            assert "x-api-key" in headers
            assert json["order_id"] == "42"
            return DummyResp({"payment_id": "P1", "invoice_url": "https://pay.example/x"})

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    gw = NowPaymentsGateway(api_key="API", ipn_secret="secret")
    r = await gw.create_payment(amount=1.0, order_id="42", callback_url="https://cb.example/x", currency="USD")
    assert r["payment_id"] == "P1"


