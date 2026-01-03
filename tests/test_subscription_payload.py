from services.subscription import build_subscription_payload


def test_subscription_payload_base64() -> None:
    s = build_subscription_payload(["vless://uuid@host:443#x"])
    # base64 decode should contain the link and newline
    import base64

    raw = base64.b64decode(s.encode("ascii")).decode("utf-8")
    assert "vless://uuid@host:443#x" in raw
    assert raw.endswith("\n")



