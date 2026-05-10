"""Markdown text sanitization utilities."""

import re

_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_MD_ULIST_RE = re.compile(r"^\s*[-*+]\s+")
_MD_OLIST_RE = re.compile(r"^\s*(\d+)\.\s+")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")


def _sanitize_markdown_text(text: str) -> str:
    """Remove common markdown markers while preserving readable content."""

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = str(raw_line or "").strip()
        if not line:
            continue

        line = _MD_HEADING_RE.sub("", line)
        if _MD_ULIST_RE.match(line):
            line = _MD_ULIST_RE.sub("", line).strip()
            if line:
                line = f"\u2022 {line}"
        else:
            line = _MD_OLIST_RE.sub(lambda m: f"{m.group(1)}. ", line)

        line = _MD_LINK_RE.sub(r"\1", line)
        line = _MD_CODE_RE.sub(r"\1", line)

        while True:
            replaced = _MD_BOLD_RE.sub(
                lambda m: str(m.group(1) or m.group(2) or ""),
                line,
            )
            if replaced == line:
                break
            line = replaced

        line = line.strip()
        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _normalize_footer_brand_text(text: str) -> str:
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())
