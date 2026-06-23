from app.prompt.builder import format_transcript, format_meta


def to_markdown(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"# {title}\n\n```\n{body}\n```\n"


def to_txt(title: str, transcript: dict, meta=None) -> str:
    body = format_meta(meta) + format_transcript(transcript)
    return f"{title}\n\n{body}\n"
