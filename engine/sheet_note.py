"""The student's spreadsheet, as the tutor reads it.

When the student sends a message and the spreadsheet on the board has changed
since their last one, the page sends the sheet with it (static/sheet.js). The
tutor gets it appended to the student's message; the board shows only the
message.  An empty string means the student cleared the sheet."""

from __future__ import annotations   # the plugin runs on Python 3.9

MAX_SHEET = 8000


def with_sheet(message: str, sheet: str | None) -> str:
    """The message the tutor gets: the student's words, then the sheet."""
    if sheet is None:
        return message
    sheet = sheet.strip()[:MAX_SHEET]
    body = sheet if sheet else "(empty: the student cleared it)"
    return (f"{message}\n\n[The student's spreadsheet, sent by the app with this message: each "
            f"filled cell, with the value a formula shows after the arrow.]\n{body}")
