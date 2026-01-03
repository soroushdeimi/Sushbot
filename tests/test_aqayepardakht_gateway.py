
import pytest


@pytest.mark.asyncio
async def test_aqayepardakht_create_payment_builds_startpay_url(monkeypatch):
    from integrations.payments.aqayepardakht import AqayepardakhtGateway

    # Patch httpx.AsyncClient to avoid network
    class DummyResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class DummyClient:
        def __init__(self, *a, **k):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, *, method, url, headers, json):
            self.calls.append((method, url, headers, json))
            return DummyResp({"status": "success", "transid": "T123"})

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    gw = AqayepardakhtGateway(pin="PIN123")
    res = await gw.create_payment(amount=10000, order_id="42", callback_url="https://cb.example/x")
    assert res["transid"] == "T123"
    assert res["payment_url"].endswith("/startpay/T123")


