"""Convert the compose editor's content (a Tk Text widget with tags) to HTML.

Input is the list produced by Text.dump(..., tag=True, text=True): tuples of
(key, value, index) where key is 'tagon', 'tagoff' or 'text'.

Tag names used by the editor:
    fg_RRGGBB   text colour        bold   italic
Text without a colour tag gets NO colour in the e-mail, so the reader's own
theme decides. This stops white-on-white text when you write in dark mode.
"""
import html
import re
from typing import Iterable, Tuple

COLOR_TAG = re.compile(r"^fg_([0-9a-fA-F]{6})$")


def color_tag(hex_color: str) -> str:
    return "fg_" + hex_color.lstrip("#").lower()


def dump_to_html(items: Iterable[Tuple[str, str, str]]) -> str:
    active = []          # tag names currently on, in order
    out = []
    for key, value, _ in items:
        if key == "tagon":
            if value not in active:
                active.append(value)
        elif key == "tagoff":
            if value in active:
                active.remove(value)
        elif key == "text":
            style = []
            for t in active:
                m = COLOR_TAG.match(t)
                if m:
                    style = [s for s in style if not s.startswith("color:")]
                    style.append("color:#" + m.group(1).lower())
                elif t == "bold":
                    style.append("font-weight:bold")
                elif t == "italic":
                    style.append("font-style:italic")
            esc = html.escape(value).replace("\n", "<br>\n")
            out.append(f'<span style="{";".join(style)}">{esc}</span>' if style else esc)
    return '<div style="font-family:sans-serif;font-size:11pt">' + "".join(out) + "</div>"
