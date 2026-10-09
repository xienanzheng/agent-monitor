from monitor.redact import redact


def test_stripe_secret_key_is_redacted():
    out = redact("export STRIPE_SECRET_KEY=sk_test_FAKEKEYFAKEKEYFAKEKEYFAKEKEY00")
    assert "sk_test_" not in out
    assert "[REDACTED:stripe_key]" in out


def test_github_tokens_are_redacted():
    out = redact("token gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 and ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert "gho_" not in out and "ghp_" not in out


def test_aws_key_and_pem_block_are_redacted():
    text = "AKIAIOSFODNN7EXAMPLE\n-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    out = redact(text)
    assert "AKIA" not in out
    assert "abc" not in out


def test_env_assignment_value_is_redacted_but_name_kept():
    out = redact("API_TOKEN=supersecretvalue123")
    assert "supersecretvalue123" not in out
    assert out.startswith("API_TOKEN=")


def test_ordinary_text_is_unchanged():
    assert redact("pytest -q && git status") == "pytest -q && git status"


def test_truncated_pem_block_without_end_line_is_redacted():
    out = redact("key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAplaceholderKeyMaterial…[+900 chars]")
    assert "MIIEow" not in out and "placeholderKeyMaterial" not in out
    assert out.startswith("key:\n[REDACTED:pem]")


def test_secret_names_in_json_quotes_flags_and_headers_are_redacted():
    cases = {
        '{"api_key": "placeholdervalue123"}': '"api_key"',
        "{'password': 'placeholdervalue123'}": "'password'",
        "mysql --password placeholdervalue123 -h db": "--password",
        "curl -H 'x-api-key: placeholdervalue123' https://example.invalid": "x-api-key",
        '{\\"client_secret\\": \\"placeholdervalue123\\"}': "client_secret",
    }
    for text, name in cases.items():
        out = redact(text)
        assert "placeholdervalue123" not in out, out
        assert name in out and "[REDACTED:value]" in out, out


def test_flag_redaction_does_not_swallow_the_next_flag():
    assert redact("tool --api-key --verbose") == "tool --api-key --verbose"


def test_email_addresses_are_redacted():
    out = redact("git config user.email someone.placeholder@example.com && echo done")
    assert "someone.placeholder" not in out and "example.com" not in out
    assert "[REDACTED:email]" in out and out.endswith("&& echo done")


def test_url_credentials_are_redacted_but_scheme_and_host_kept():
    out = redact("psql postgres://admin:placeholderpass@db.example.com:5432/app")
    assert "admin" not in out and "placeholderpass" not in out
    assert "postgres://" in out and "@db.example.com:5432/app" in out


def test_redaction_stays_fast_on_long_identifier_runs():
    import time

    # whole tool outputs are redacted before clipping, so pathological text must not go quadratic
    for text in ("key" * 20_000, "API_KEY_" * 8_000, "a.b" * 20_000 + "@"):
        t0 = time.perf_counter()
        redact(text)
        assert time.perf_counter() - t0 < 1.0
