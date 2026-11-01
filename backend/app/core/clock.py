"""Single source of "now" for stored timestamps.

All timestamps are stored as naive UTC so values are the same whether the
server runs on Render (UTC) or a local machine (e.g. Asia/Manila). The admin
dashboard converts them to the viewer's local time for display.
"""

import datetime


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
