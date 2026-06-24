import re
from urllib.parse import quote

from app.prompt.builder import format_transcript, format_meta


def content_disposition(title: str, ext: str, fallback: str) -> str:
    """Build a Content-Disposition that downloads as the meeting title, not the id.

    Emits both an ASCII `filename=` (sanitized, falls back to the id when the title
    has no ASCII word chars, e.g. a Korean-only title) and an RFC 5987 `filename*=`
    carrying the real UTF-8 title — browsers prefer the latter.
    """
    base = (title or "").strip().replace("\r", " ").replace("\n", " ") or fallback
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or fallback
    encoded = quote(f"{base}.{ext}", safe="")
    return f"attachment; filename=\"{ascii_name}.{ext}\"; filename*=UTF-8''{encoded}"


def to_markdown(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"# {title}\n\n```\n{body}\n```\n"


def to_txt(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"{title}\n\n{body}\n"
