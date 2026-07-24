from app.config import Settings
from app.security import SessionManager


def test_signed_session_rejects_tampering():
    manager = SessionManager(
        Settings(
            app_access_code="demo-code",
            session_secret="a-secure-test-secret-with-at-least-32-characters",
        )
    )
    session, token = manager.issue(
        authenticated=True,
        auth_provider="feishu",
        principal_id=manager.principal_id("feishu", "ou_example"),
        display_name="测试用户",
    )

    assert manager.parse(token) == session
    replacement = "0" if token[-1] != "0" else "1"
    assert manager.parse(f"{token[:-1]}{replacement}") is None
    assert manager.verify_access_code("demo-code") is True
    assert manager.verify_access_code("wrong-code") is False


def test_oauth_state_is_signed_and_expires(monkeypatch):
    manager = SessionManager(
        Settings(session_secret="a-secure-test-secret-with-at-least-32-characters")
    )
    state, token = manager.create_oauth_state()

    assert manager.verify_oauth_state(state, token) is True
    assert manager.verify_oauth_state("wrong-state", token) is False
    replacement = "0" if token[-1] != "0" else "1"
    assert manager.verify_oauth_state(state, f"{token[:-1]}{replacement}") is False

    monkeypatch.setattr("app.security.time.time", lambda: 4_102_444_800)
    assert manager.verify_oauth_state(state, token) is False
