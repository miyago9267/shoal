"""rating: star rating with an optional comment."""
from .. import validate


def handle(payload):
    return {
        "item_id": validate.int_field(payload, "item_id", lo=1),
        "stars": validate.int_field(payload, "stars", lo=1, hi=5),
        "comment": validate.str_field(payload, "comment", 0, 500, required=False) or None,
    }
