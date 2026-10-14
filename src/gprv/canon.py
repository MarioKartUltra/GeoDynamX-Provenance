"""Canonical bytes (RFC 8785) and the value rules of spec §3."""
import hashlib
import math

import rfc8785

SAFE_INT = 2**53 - 1                 # RFC 8785 / I-JSON: integers exactly representable as IEEE-754 doubles


class CanonicalError(ValueError):
    """A value has no canonical form."""


def canonical(obj) -> bytes:
    """RFC 8785 bytes of ``obj``; non-finite floats and unsafe integers are refused."""
    try:
        return rfc8785.dumps(obj)
    except rfc8785.CanonicalizationError as e:
        raise CanonicalError(str(e)) from e


def normalize(obj):
    """Apply the value rules: non-finite floats and unsafe integers become strings, tuples become lists,
    numpy scalars and arrays become plain Python values."""
    if hasattr(obj, "tolist") and not isinstance(obj, (str, bytes)):     # numpy array or scalar
        return normalize(obj.tolist())
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj if -SAFE_INT <= obj <= SAFE_INT else str(obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonicalError(f"object key {k!r} is not a string")
            out[k] = normalize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    raise CanonicalError(f"unsupported type: {type(obj).__name__}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
