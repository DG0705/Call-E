from call_e_shared import AuthContext


def test_auth_context_defaults_to_anonymous() -> None:
    context = AuthContext()

    assert context.subject_id is None
    assert context.session_id is None
    assert context.is_authenticated is False


def test_auth_context_supports_future_session_identity() -> None:
    context = AuthContext(subject_id="subject-123", session_id="session-123")

    assert context.is_authenticated is True
