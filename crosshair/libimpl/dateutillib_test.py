import datetime

from dateutil.relativedelta import relativedelta

from crosshair.statespace import POST_FAIL
from crosshair.test_util import check_states


def test_period_year_clamp_fail() -> None:
    def f(d: datetime.date) -> datetime.date:
        """
        Adding one year to Feb 29 clamps to Feb 28 of the (non-leap) next year.

        pre: d == datetime.date(2000, 2, 29)
        post: _ != datetime.date(2001, 2, 28)
        """
        return d + relativedelta(years=1)

    check_states(f, POST_FAIL)


def test_period_stays_symbolic_fail() -> None:
    # The added year/month/day must remain symbolic so a specific target date
    # is reachable, rather than realizing `d` during the arithmetic.
    def f(d: datetime.date) -> datetime.date:
        """
        pre: datetime.date(1900, 1, 1) <= d <= datetime.date(2090, 1, 1)
        post: _ != datetime.date(2057, 9, 14)
        """
        return d + relativedelta(years=3, months=2)

    check_states(f, POST_FAIL)
