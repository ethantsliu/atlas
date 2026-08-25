"""Constrain remote retrieval to public HTTPS resources."""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.request
from urllib.parse import urlsplit


HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
LOCAL_SUFFIXES = (".internal", ".local", ".localhost")


def is_public_url(value: object) -> bool:
    """Accept a credential-free HTTPS URL with a public-looking host."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return False
    host = parsed.hostname.rstrip(".").lower()
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    return (
        len(labels) >= 2
        and not ascii_host.endswith(LOCAL_SUFFIXES)
        and all(HOST_LABEL.fullmatch(label) for label in labels)
    )


def public_host(host: str, port: int = 443) -> bool:
    """Resolve a host and require every address to be globally routable."""
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = {ipaddress.ip_address(row[4][0]) for row in rows}
    except (OSError, ValueError):
        return False
    return bool(addresses) and all(address.is_global for address in addresses)


def require_public_url(value: object) -> str:
    """Return one retrievable URL or reject its scheme, host, or DNS result."""
    if not is_public_url(value):
        raise RuntimeError(f"Remote source must use public HTTPS: {value}")
    url = str(value)
    host = urlsplit(url).hostname
    if host is None or not public_host(host):
        raise RuntimeError(f"Remote source resolves outside public IP space: {url}")
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Validate every redirect target before urllib follows it."""

    def redirect_request(self, request, handle, code, message, headers, new_url):
        require_public_url(new_url)
        return super().redirect_request(
            request,
            handle,
            code,
            message,
            headers,
            new_url,
        )


def open_public(request: urllib.request.Request, timeout: float):
    """Open a public HTTPS request and recheck the final response URL."""
    return open_safe(safe_opener(), request, timeout)


def safe_opener(*handlers):
    """Build an opener that validates each HTTP redirect target."""
    return urllib.request.build_opener(SafeRedirect(), *handlers)


def open_safe(opener, request: urllib.request.Request, timeout: float):
    """Open through one supplied session and recheck the final response URL."""
    require_public_url(request.full_url)
    response = opener.open(request, timeout=timeout)
    try:
        require_public_url(response.geturl())
    except BaseException:
        response.close()
        raise
    return response


def read_limited(response, limit: int) -> bytes:
    """Read a small response without allowing an unbounded allocation."""
    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise RuntimeError(f"Remote response exceeds {limit} bytes")
        except ValueError as error:
            raise RuntimeError("Remote response has invalid Content-Length") from error
    body = bytearray()
    while True:
        chunk = response.read(min(65_536, limit + 1 - len(body)))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > limit:
            raise RuntimeError(f"Remote response exceeds {limit} bytes")
