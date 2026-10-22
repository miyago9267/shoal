"""tables: u32 row count; rows of (id u16, flag u8, name u8-len latin-1, 2 reserved).

The two reserved bytes of the final row may be missing.
"""
from .errors import ParseError
from .reader import Reader, ReaderError


def parse(data):
    r = Reader(data)
    try:
        count = r.u32()
        rows = []
        for index in range(count):
            ident = r.u16()
            flag = r.u8()
            size = r.u8()
            name = r.string(size)
            if len(name) != size:
                raise ParseError("row %d: name is cut short" % index)
            r.skip(2)
            rows.append({"id": ident, "flag": flag, "name": name})
    except ReaderError as exc:
        raise ParseError(str(exc)) from None
    return rows


def by_id(rows):
    return {row["id"]: row for row in rows}


def flagged(rows):
    return [row["id"] for row in rows if row["flag"]]
