"""Plain-text table rendering.

Shared with the invoicing CLI: output must stay byte-for-byte stable.
"""
import re


def _cell(value):
    text = str(value)
    # Collapse internal whitespace so a cell never wraps.
    return re.compile(r"\s+").sub(" ", text).strip()


def render_table(headers, rows):
    table = [list(map(_cell, headers))] + [list(map(_cell, row)) for row in rows]
    widths = []
    for col in range(len(headers)):
        width = 0
        for row in table:
            if len(row[col]) > width:
                width = len(row[col])
        widths.append(width)
    out = ""
    for i, row in enumerate(table):
        line = ""
        for col, cell in enumerate(row):
            if col > 0:
                line = line + " | "
            line = line + cell.ljust(widths[col])
        out = out + line.rstrip() + "\n"
        if i == 0:
            out = out + "-+-".join("-" * w for w in widths) + "\n"
    return out.rstrip("\n")
