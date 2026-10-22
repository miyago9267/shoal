"""address: shipping address."""
import re

from .. import validate
from ..errors import ValidationError

ZIP = {
    "US": re.compile(r"\d{5}(-\d{4})?"),
    "TW": re.compile(r"\d{3}(\d{2,3})?"),
    "JP": re.compile(r"\d{3}-\d{4}"),
    "GB": re.compile(r"[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}"),
}


def handle(payload):
    country = validate.choice_field(payload, "country", ZIP)
    zip_code = validate.str_field(payload, "zip", 1, 12)
    if not ZIP[country].fullmatch(zip_code):
        raise ValidationError("zip", "does not match the %s format" % country)
    return {
        "line1": validate.str_field(payload, "line1", 1, 80),
        "city": validate.str_field(payload, "city", 1, 40),
        "country": country,
        "zip": zip_code,
    }
