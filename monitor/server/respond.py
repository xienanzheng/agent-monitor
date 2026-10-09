"""Every API response goes through ok(): all strings are redacted again (defence in depth)."""
import math

from fastapi.responses import JSONResponse

from monitor.redact import redact


def redact_obj(x):
    if isinstance(x, str):
        return redact(x)
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, (list, tuple)):
        return [redact_obj(v) for v in x]
    if isinstance(x, dict):
        return {k: redact_obj(v) for k, v in x.items()}
    return x


def ok(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(redact_obj(data), status_code=status_code)
