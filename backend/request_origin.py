"""Exact browser Origin checks with explicit deployment origins behind a proxy."""
import os
from urllib.parse import urlsplit


def normalize_origin(value):
    if not value or any(ch.isspace() for ch in value):
        return None
    try:
        url = urlsplit(value)
        if (url.scheme not in ('http', 'https') or not url.hostname
                or url.username is not None or url.password is not None
                or url.path not in ('', '/') or url.query or url.fragment):
            return None
        port = url.port if url.port is not None else (443 if url.scheme == 'https' else 80)
        return url.scheme, url.hostname.lower(), port
    except ValueError:
        return None


def origin_allowed(origin, host, scheme):
    parsed = normalize_origin(origin)
    if parsed is None:
        return False
    # Host rewriting is common at the Studio proxy. Trust only exact origins
    # configured by the operator, never client-provided forwarded headers.
    configured = {
        normalized for item in os.getenv('HUAWEI_ALLOWED_ORIGINS', '').split(',')
        if (normalized := normalize_origin(item.strip())) is not None
    }
    return parsed == normalize_origin(f'{scheme}://{host}') or parsed in configured
