from app.prompt.builder import format_transcript


def to_markdown(title: str, transcript: dict) -> str:
    body = format_transcript(transcript)
    return f"# {title}\n\n```\n{body}\n```\n"


def to_txt(title: str, transcript: dict) -> str:
    body = format_transcript(transcript)
    return f"{title}\n\n{body}\n"
