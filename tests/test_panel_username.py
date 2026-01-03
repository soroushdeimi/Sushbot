from utils.panel_username import make_panel_username


def test_make_panel_username_basic() -> None:
    u = make_panel_username(telegram_username="MyUserName", user_id=123, suffix="7")
    assert u.startswith("myusername-123-7")
    assert len(u) <= 128


def test_make_panel_username_no_username() -> None:
    u = make_panel_username(telegram_username=None, user_id=1, suffix="trial")
    assert u.startswith("user-1-trial")


def test_make_panel_username_truncation() -> None:
    long = "a" * 300
    u = make_panel_username(telegram_username=long, user_id=999, suffix="999")
    assert u.endswith("-999-999")
    assert len(u) == 128
