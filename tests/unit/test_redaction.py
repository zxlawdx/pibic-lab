from pibic_lab_core.security.redaction import redact, redact_text


def test_redacts_nested_secrets():
    data = {
        "username": "pibic",
        "password": "abc123",
        "nested": {"token": "secret-token", "safe": "value"},
    }
    cleaned = redact(data)
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["safe"] == "value"


def test_redacts_authorization_and_url_passwords():
    text = "Authorization: PVEAPIToken=x password=abc https://user:pass@example.org/path"
    cleaned = redact_text(text)
    assert "PVEAPIToken=x" not in cleaned
    assert "password=abc" not in cleaned
    assert "user:pass@" not in cleaned
    assert "[REDACTED]" in cleaned
