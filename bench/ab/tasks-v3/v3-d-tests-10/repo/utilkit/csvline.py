"""csvline: one line of comma separated values."""


def join_csv_line(fields):
    """Quote fields that contain a comma, a quote or a newline."""
    out = []
    for field in fields:
        if any(ch in field for ch in ',"\n'):
            field = '"' + field.replace('"', '""') + '"'
        out.append(field)
    return ",".join(out)


# TODO(fix): split_csv_line(line) must
#   * treat a field that starts with a double quote as quoted: commas inside it
#     do not split, and a doubled quote ("") stands for one literal quote,
#   * leave quotes in the middle of an unquoted field alone,
#   * keep whitespace and empty fields as they are ("a,,b" has three fields, a
#     trailing comma adds an empty last field, an empty line is [""]),
#   * raise ValueError for an unterminated quote and for text between a closing
#     quote and the next comma.


def split_csv_line(line):
    """Split ``line`` into fields."""
    return line.split(",")


def roundtrip_ok(fields):
    return split_csv_line(join_csv_line(fields)) == list(fields)


def column(lines, index):
    return [split_csv_line(ln)[index] for ln in lines]


def pad(fields, count):
    """Pad with empty strings or fail when there are too many fields."""
    if len(fields) > count:
        raise ValueError("too many fields")
    return list(fields) + [""] * (count - len(fields))


def to_dict(header, fields):
    if len(header) != len(fields):
        raise ValueError("header and row differ in length")
    return dict(zip(header, fields))


def strip_all(fields):
    return [f.strip() for f in fields]


def count_fields(line):
    return len(line.split(","))
