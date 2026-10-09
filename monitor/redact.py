"""Remove secrets before anything is written to disk or shown in a report.

Pattern-based, best effort: it catches common credential formats, secret-named assignments,
emails and URL credentials, not every secret a log can contain."""
import re

_PATTERNS = [
    # an END line may be missing when the block was truncated upstream: redact to end of text
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("stripe_key", re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{10,}")),
    ("github_token", re.compile(r"\bgh[opsur]_[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer", re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{20,}")),
]
# Repetitions next to a search anchor are bounded ({0,64}) so long runs of identifier-like text stay
# linear: redaction runs on whole tool outputs before they are clipped.
# scheme://user:pass@host -> keep scheme and host, drop user:pass
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]{0,30}://)[^\s/@:'\"]+:[^\s/@'\"]+@")
# emails; the conventional git@host SSH user is not personal and keeps remotes readable
_EMAIL = re.compile(r"(?<![\w.%+-])(?!git@)[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")

# Secret-bearing names: API_TOKEN, api_key, x-api-key, client-secret, ...
_NAME = r"[A-Z0-9_-]{0,64}(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL)[A-Z0-9_-]{0,64}"
_Q = r"""\\?["']"""  # a quote, possibly backslash-escaped (JSON inside a JSON string)
# NAME=value, NAME: value, "NAME": "value", 'NAME': 'value', \"NAME\": \"value\"; keep the name, drop the value
_ENV = re.compile(
    rf"""(?i)(?<![A-Z0-9_-])((?:{_Q})?{_NAME}(?:{_Q})?\s*[=:]\s*)"""
    rf"""(?:({_Q})(?!\[REDACTED)([^"'\n\\]{{6,}})\2|(?!\[REDACTED)([^\s'"]{{6,}}))""")
# --password value, --api-key "value" (a following --flag is not a value)
_FLAG = re.compile(
    rf"""(?i)(?<![A-Z0-9_-])(--{_NAME}\s+)(?:(["'])(?!\[REDACTED)([^"'\n]{{6,}})\2|(?![-"']|\[REDACTED)([^\s'"]{{6,}}))""")


def _keep_name(m: re.Match) -> str:
    q = m.group(2) or ""
    return f"{m.group(1)}{q}[REDACTED:value]{q}"


def redact(text: str) -> str:
    if not text:
        return text
    for name, pat in _PATTERNS:
        if name == "bearer":
            text = pat.sub(lambda m: m.group(1) + "[REDACTED:token]", text)
        else:
            text = pat.sub(f"[REDACTED:{name}]", text)
    text = _URL_CREDS.sub(lambda m: m.group(1) + "[REDACTED:credentials]@", text)
    text = _EMAIL.sub("[REDACTED:email]", text)
    text = _ENV.sub(_keep_name, text)
    return _FLAG.sub(_keep_name, text)
