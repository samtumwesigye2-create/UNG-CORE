from app.api.auth_routes import CALLBACK_PATH, CLIENT_ID
from app.api.security import SESSION_COOKIE


def test_core_sso_contract():
    assert CLIENT_ID == "UNG-CORE"
    assert CALLBACK_PATH == "/auth/callback"
    assert SESSION_COOKIE == "ung_core_session"


def test_browser_session_cookie_is_distinct_from_iam_cookie():
    assert SESSION_COOKIE != "ung_iam_session"
