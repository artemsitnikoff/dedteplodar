"""Convert the generator's Telegram-flavoured HTML into Bitrix24 BBCode.

Bitrix24 chat renders BBCode only (no Markdown, no HTML). Our answers are
HTML with a tiny tag set (``b, i, code, a, br`` — see the web-chat sanitizer
allowlist), so a handful of regex passes is enough. URLs are converted while
still wrapped in their ``<a href>`` so nothing downstream can mangle
underscores inside them (the ``kaskad_12_t`` lesson from ``_md_to_html``).
"""
from __future__ import annotations

import html
import re

_A_RE = re.compile(r"<a\s+[^>]*?href=([\"'])(.*?)\1[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_P_CLOSE_RE = re.compile(r"</p\s*>", re.IGNORECASE)
_LI_OPEN_RE = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_LI_CLOSE_RE = re.compile(r"</li\s*>", re.IGNORECASE)
_SIMPLE_TAGS = (
    (re.compile(r"<(b|strong)\b[^>]*>", re.IGNORECASE), "[b]"),
    (re.compile(r"</(b|strong)\s*>", re.IGNORECASE), "[/b]"),
    (re.compile(r"<(i|em)\b[^>]*>", re.IGNORECASE), "[i]"),
    (re.compile(r"</(i|em)\s*>", re.IGNORECASE), "[/i]"),
    (re.compile(r"<(u)\b[^>]*>", re.IGNORECASE), "[u]"),
    (re.compile(r"</(u)\s*>", re.IGNORECASE), "[/u]"),
    (re.compile(r"<(s|strike|del)\b[^>]*>", re.IGNORECASE), "[s]"),
    (re.compile(r"</(s|strike|del)\s*>", re.IGNORECASE), "[/s]"),
    (re.compile(r"<(code|pre)\b[^>]*>", re.IGNORECASE), "[code]"),
    (re.compile(r"</(code|pre)\s*>", re.IGNORECASE), "[/code]"),
)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def html_to_bbcode(text: str) -> str:
    """HTML (b/i/u/s/code/a/br + stray tags) → Bitrix24 BBCode.

    Entities are unescaped *last*, after every tag has been translated, so
    literal ``&lt;b&gt;`` in the answer text can never turn into markup.
    """
    if not text:
        return ""
    out = text.replace("\r\n", "\n")

    def _link(m: re.Match) -> str:
        url = html.unescape(m.group(2)).strip()
        label = m.group(3).strip()
        if not url:
            return label
        if not label or label == url:
            return f"[url]{url}[/url]"
        return f"[url={url}]{label}[/url]"

    out = _A_RE.sub(_link, out)
    out = _BR_RE.sub("\n", out)
    out = _P_CLOSE_RE.sub("\n\n", out)
    out = _LI_OPEN_RE.sub("• ", out)
    out = _LI_CLOSE_RE.sub("\n", out)
    for pattern, replacement in _SIMPLE_TAGS:
        out = pattern.sub(replacement, out)
    out = _ANY_TAG_RE.sub("", out)
    out = html.unescape(out)
    out = _MULTI_NL_RE.sub("\n\n", out)
    return out.strip()
