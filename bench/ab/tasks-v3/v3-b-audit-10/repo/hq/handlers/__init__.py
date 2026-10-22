"""Handler registry."""
from . import (
    address, coupon, invite, profile, rating, schedule, search, signup,
    transfer, upload,
)

HANDLERS = {
    "address": address.handle,
    "coupon": coupon.handle,
    "invite": invite.handle,
    "profile": profile.handle,
    "rating": rating.handle,
    "schedule": schedule.handle,
    "search": search.handle,
    "signup": signup.handle,
    "transfer": transfer.handle,
    "upload": upload.handle,
}
