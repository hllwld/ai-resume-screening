from app.config import Settings
from app.security import SessionManager


def test_signed_session_rejects_tampering():
    manager = SessionManager(
        Settings(
            app_access_code="demo-code",
            session_secret="a-secure-test-secret-with-at-least-32-characters",
        )
    )
    session, token = manager.issue(authenticated=True)

    assert manager.parse(token) == session
    assert manager.parse(f"{token[:-1]}0") is None
    assert manager.verify_access_code("demo-code") is True
    assert manager.verify_access_code("wrong-code") is False
