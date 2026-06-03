"""Symbolic support for :mod:`dateutil.relativedelta`.

``date + relativedelta`` dispatches ``__radd__`` through the C-level ``+``
operator, which CrossHair's function-call patching never sees, so instead we
wrap CrossHair's own ``date.__add__``/``__sub__`` to apply a relative
year/month/day "Period" symbolically (the stdlib path realizes the date via
``calendar.monthrange`` and reconstruction).  Only the relative
year/month/day form is handled; anything richer falls back to ``dateutil``.
"""

from crosshair.libimpl import datetimelib
from crosshair.tracers import NoTracing

try:
    from dateutil.relativedelta import relativedelta
except ImportError:  # pragma: no cover
    relativedelta = None


def _is_period(rd) -> bool:
    """True iff ``rd`` sets only relative years/months/days."""
    return rd == relativedelta(years=rd.years, months=rd.months, days=rd.days)


def _apply(d, rd):
    """``d + relativedelta(years, months, days)``, kept symbolic.

    Add years and months (carrying the month into the year), clamp the day to
    the resulting month's length, then add the day offset.  Uses only
    arithmetic and the branch-free ``_days_in_month``.
    """
    month0 = (d.month - 1) + rd.months
    year = d.year + rd.years + month0 // 12
    month = month0 % 12 + 1
    ndays = datetimelib._days_in_month(year, month)
    day = d.day
    day = day + (ndays - day) * (day > ndays)  # branch-free min(day, ndays)
    result = datetimelib.date(year, month, day)
    return result + datetimelib.timedelta(days=rd.days) if rd.days else result


def make_registrations():
    if relativedelta is None:  # pragma: no cover
        return
    cls = datetimelib.date
    if getattr(cls, "_crosshair_relativedelta_wrapped", False):
        return
    add, sub = cls.__add__, cls.__sub__

    def __add__(self, other):
        with NoTracing():
            period = isinstance(other, relativedelta) and _is_period(other)
        return _apply(self, other) if period else add(self, other)

    def __sub__(self, other):
        with NoTracing():
            period = isinstance(other, relativedelta) and _is_period(other)
        return _apply(self, -other) if period else sub(self, other)

    cls.__add__ = cls.__radd__ = __add__
    cls.__sub__ = __sub__
    cls._crosshair_relativedelta_wrapped = True
