"""wrap: greedy text wrapping."""
import re


def indent(text, prefix):
    """Prefix every non-empty line."""
    return "\n".join(prefix + ln if ln else ln for ln in text.split("\n"))


def count_lines(text):
    return len(text.split("\n")) if text else 0


# TODO(fix): wrap(text, width) must
#   * wrap each paragraph separately (paragraphs are separated by blank lines)
#     and join the paragraphs with exactly one blank line between them,
#   * collapse whitespace inside a paragraph, greedy filling up to width columns,
#   * hard-split a word longer than width into width-sized pieces (the last piece
#     may be shorter and continues the line fill),
#   * return "" for blank input and raise ValueError when width < 1.


def wrap(text, width):
    """Wrap ``text`` to ``width`` columns."""
    if width < 1:
        raise ValueError("width must be positive")
    lines = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return "\n".join(lines)


def fill(text, width, prefix=""):
    """Wrap and indent in one go."""
    return indent(wrap(text, width - len(prefix)), prefix)


def center(line, width):
    """Centre one line; lines wider than width are returned unchanged."""
    if len(line) >= width:
        return line
    left = (width - len(line)) // 2
    return " " * left + line


def longest_line(text):
    return max((len(ln) for ln in text.split("\n")), default=0)


def dedent_lines(lines):
    """Remove the indentation common to all non-blank lines."""
    margin = None
    for ln in lines:
        if ln.strip():
            lead = len(ln) - len(ln.lstrip())
            margin = lead if margin is None else min(margin, lead)
    margin = margin or 0
    return [ln[margin:] for ln in lines]


def truncate(text, width, marker="..."):
    if width < len(marker):
        raise ValueError("width smaller than marker")
    return text if len(text) <= width else text[: width - len(marker)] + marker
