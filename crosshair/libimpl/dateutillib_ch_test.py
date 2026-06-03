import sys
from datetime import date

import pytest  # type: ignore
from dateutil.relativedelta import relativedelta

from crosshair.core_and_libs import MessageType, analyze_function, run_checkables
from crosshair.test_util import ResultComparison, compare_results

# crosshair: max_uninteresting_iterations=20


def _plus(rd):
    return lambda d: d + rd


def _minus(rd):
    return lambda d: d - rd


def check_plus_one_year(d: date) -> ResultComparison:
    """post: _"""
    # Exercises end-of-month day clamping (e.g. Feb 29 -> Feb 28).
    return compare_results(_plus(relativedelta(years=1)), d)


def check_plus_one_month(d: date) -> ResultComparison:
    """post: _"""
    # Exercises month overflow and clamping (e.g. Jan 31 -> Feb 28/29).
    return compare_results(_plus(relativedelta(months=1)), d)


def check_plus_thirteen_months(d: date) -> ResultComparison:
    """post: _"""
    return compare_results(_plus(relativedelta(months=13)), d)


def check_plus_days(d: date) -> ResultComparison:
    """post: _"""
    # Day offset crossing month/year boundaries.
    return compare_results(_plus(relativedelta(days=400)), d)


def check_plus_mixed_period(d: date) -> ResultComparison:
    """post: _"""
    return compare_results(_plus(relativedelta(years=2, months=5, days=10)), d)


def check_minus_mixed_period(d: date) -> ResultComparison:
    """post: _"""
    return compare_results(_minus(relativedelta(years=1, months=7, days=3)), d)


@pytest.mark.parametrize("fn_name", [fn for fn in dir() if fn.startswith("check_")])
def test_builtin(fn_name: str) -> None:
    this_module = sys.modules[__name__]
    messages = run_checkables(analyze_function(getattr(this_module, fn_name)))
    errors = [m for m in messages if m.state > MessageType.PRE_UNSAT]
    assert errors == []
