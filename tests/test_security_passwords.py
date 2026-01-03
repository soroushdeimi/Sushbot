from utils.security import hash_password, verify_password


def test_long_password_ok() -> None:
    pw = "x" * 200
    h = hash_password(pw)
    assert verify_password(pw, h) is True
    assert verify_password("y" * 200, h) is False
