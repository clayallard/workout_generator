"""Phone delivery through the public ntfy service."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


NTFY_SERVER = "https://ntfy.sh"
MAX_MESSAGE_BYTES = 3900


def publish_markdown(
    topic: str,
    markdown: str,
    title: str,
    server: str = NTFY_SERVER,
) -> int:
    """Publish Markdown in renderable chunks and return the message count."""
    chunks = split_markdown(markdown)
    if not chunks:
        raise ValueError("Notification text is required.")

    endpoint = f"{server.rstrip('/')}/{quote(topic, safe='')}"
    for index, chunk in enumerate(chunks, start=1):
        message_title = title if len(chunks) == 1 else f"{title} ({index}/{len(chunks)})"
        request = Request(
            endpoint,
            data=chunk.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Markdown": "yes",
                "Title": message_title,
                "Tags": "muscle",
                "Click": endpoint,
                "Actions": f"view, Open formatted workout, {endpoint}",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status >= 400:
                    raise RuntimeError(f"ntfy returned HTTP {response.status}.")
        except HTTPError as exc:
            raise RuntimeError(f"ntfy rejected the notification (HTTP {exc.code}).") from exc
        except (TimeoutError, URLError) as exc:
            raise RuntimeError("Could not reach ntfy. Check the computer's internet connection.") from exc

    return len(chunks)


def publish_html_attachment(
    topic: str,
    html: str,
    title: str,
    filename: str,
    server: str = NTFY_SERVER,
) -> int:
    """Publish a standalone HTML workout as an ntfy file attachment."""
    endpoint = f"{server.rstrip('/')}/{quote(topic, safe='')}"
    request = Request(
        endpoint,
        data=html.encode("utf-8"),
        method="PUT",
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Title": title,
            "Message": "Tap the attached workout to open the formatted view.",
            "Filename": filename,
            "Tags": "muscle",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status >= 400:
                raise RuntimeError(f"ntfy returned HTTP {response.status}.")
    except HTTPError as exc:
        raise RuntimeError(f"ntfy rejected the workout attachment (HTTP {exc.code}).") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("Could not reach ntfy. Check the computer's internet connection.") from exc
    return 1


def split_markdown(markdown: str, max_bytes: int = MAX_MESSAGE_BYTES) -> list[str]:
    """Split text on line boundaries so each ntfy message remains renderable."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive.")

    chunks: list[str] = []
    current = ""
    for line in markdown.strip().splitlines(keepends=True):
        for piece in _split_oversized_text(line, max_bytes):
            if current and len((current + piece).encode("utf-8")) > max_bytes:
                chunks.append(current.rstrip())
                current = ""
            current += piece

    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def _split_oversized_text(text: str, max_bytes: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for character in text:
        if current and len((current + character).encode("utf-8")) > max_bytes:
            pieces.append(current)
            current = ""
        current += character
    if current:
        pieces.append(current)
    return pieces
