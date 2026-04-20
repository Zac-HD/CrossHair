import time

import pytest
import z3  # type: ignore

from crosshair.core import Patched, proxy_for_type
from crosshair.statespace import (
    CallAnalysis,
    HeapRef,
    RootNode,
    SimpleStateSpace,
    SnapshotRef,
    StateSpace,
    StateSpaceContext,
    VerificationStatus,
    model_value_to_python,
)
from crosshair.tracers import COMPOSITE_TRACER, NoTracing, ResumedTracing
from crosshair.util import IgnoreAttempt, UnknownSatisfiability

_HEAD_SNAPSHOT = SnapshotRef(-1)


def test_find_key_in_heap():
    space = SimpleStateSpace()
    listref = z3.Const("listref", HeapRef)
    listval1 = space.find_key_in_heap(listref, list, lambda t: [], _HEAD_SNAPSHOT)
    assert isinstance(listval1, list)
    listval2 = space.find_key_in_heap(listref, list, lambda t: [], _HEAD_SNAPSHOT)
    assert listval1 is listval2
    dictref = z3.Const("dictref", HeapRef)
    dictval = space.find_key_in_heap(dictref, dict, lambda t: {}, _HEAD_SNAPSHOT)
    assert dictval is not listval1
    assert isinstance(dictval, dict)


def test_timeout() -> None:
    num_ints = 100
    space = StateSpace(time.monotonic() + 60_000, 0.1, RootNode())
    with pytest.raises(UnknownSatisfiability):
        with Patched(), StateSpaceContext(space), COMPOSITE_TRACER:
            ints = [proxy_for_type(int, f"i{i}") for i in range(num_ints)]
            for i in range(num_ints - 2):
                t0 = time.monotonic()
                if ints[i] * ints[i + 1] == ints[i + 2]:
                    pass
                ints[i + 1] += ints[i]
    solve_time = time.monotonic() - t0
    assert 0.05 < solve_time < 0.5


def test_infinite_timeout() -> None:
    space = StateSpace(time.monotonic() + 1000, float("+inf"), RootNode())
    assert space.solver.check(True) == z3.sat


def test_checkpoint() -> None:
    space = SimpleStateSpace()
    ref = z3.Const("ref", HeapRef)

    def find_key(snapshot):
        return space.find_key_in_heap(ref, list, lambda t: [], snapshot)

    orig_snapshot = space.current_snapshot()
    listval = find_key(_HEAD_SNAPSHOT)
    space.checkpoint()

    head_listval = find_key(_HEAD_SNAPSHOT)
    head_listval.append(42)
    assert len(head_listval) == 1
    assert listval is not head_listval
    assert len(listval) == 0

    listval_again = find_key(orig_snapshot)
    assert listval_again is listval
    head_listval_again = find_key(_HEAD_SNAPSHOT)
    assert head_listval_again is head_listval


def test_model_value_to_python_AlgebraicNumRef():
    # Tests that z3.AlgebraicNumRef is handled properly.
    # See https://github.com/pschanely/CrossHair/issues/242
    rt2 = z3.simplify(z3.Sqrt(2))
    assert type(rt2) == z3.AlgebraicNumRef
    model_value_to_python(rt2)


def test_model_value_to_python_ArithRef():
    # Tests that a plain z3.ArithRef can be exported as Python
    # See https://github.com/pschanely/CrossHair/issues/381
    rt2 = z3.ToInt(2 ** z3.Int("x"))
    print("type(rt2)", type(rt2))
    assert type(rt2) == z3.ArithRef
    model_value_to_python(rt2)


def test_warm_start_choice_sequence():
    """
    A warm-started iteration should steer user-code branches toward a supplied
    concrete value without collapsing the search tree. Subsequent unseeded
    iterations must traverse the recorded tree without ``NotDeterministic``
    and naturally explore the sibling branches the seed left unvisited.
    """
    search_root = RootNode()
    branches_reached = set()

    with COMPOSITE_TRACER, NoTracing():
        for itr in range(1, 10):
            space = StateSpace(
                time.monotonic() + 30.0, 3.0, search_root=search_root
            )
            try:
                with Patched(), StateSpaceContext(space):
                    if itr == 1:
                        space.set_choice_hints([5])
                    n = proxy_for_type(int, "n")
                    if itr == 1:
                        assert space.apply_next_hint(n) is True
                    with ResumedTracing():
                        if n > 10:
                            branches_reached.add("gt")
                        else:
                            branches_reached.add("le")
                        space.detach_path()
            except IgnoreAttempt:
                pass
            space.bubble_status(CallAnalysis(VerificationStatus.CONFIRMED))
            if search_root.child.is_exhausted():
                break

    assert "le" in branches_reached
    assert "gt" in branches_reached
    assert search_root.child.is_exhausted()


def test_warm_start_does_not_taint_followup_iterations():
    """
    The seed's effect must not leak into the solver assertions of later
    iterations. Running an unseeded iteration after a warm-started one must
    be free to choose any value -- not forced to remain consistent with the
    seed.
    """
    search_root = RootNode()
    realized_after_seed = []

    with COMPOSITE_TRACER, NoTracing():
        # Iteration 1: seed n=5 and drive the program into `n <= 10`.
        space = StateSpace(time.monotonic() + 30.0, 3.0, search_root=search_root)
        with Patched(), StateSpaceContext(space):
            space.set_choice_hints([5])
            n = proxy_for_type(int, "n")
            assert space.apply_next_hint(n)
            with ResumedTracing():
                assert not (n > 10)
                space.detach_path()
        space.bubble_status(CallAnalysis(VerificationStatus.CONFIRMED))

        # Iteration 2: no seed -- the tree forces us to the `n > 10` side
        # because the other side is now exhausted. The solver must accept
        # n > 10 without any lingering `n == 5` constraint.
        space = StateSpace(time.monotonic() + 30.0, 3.0, search_root=search_root)
        with Patched(), StateSpaceContext(space):
            n = proxy_for_type(int, "n")
            with ResumedTracing():
                assert n > 10
                realized_after_seed.append(space.find_model_value(n.var))
                space.detach_path()
        space.bubble_status(CallAnalysis(VerificationStatus.CONFIRMED))

    # The realized value must exceed 10 (not be the seed value 5):
    assert realized_after_seed[0] > 10


def test_set_choice_hints_without_apply_is_noop():
    """
    Calling ``set_choice_hints`` but never applying a hint must not disturb
    the search -- the iteration behaves identically to an unseeded one.
    """
    search_root = RootNode()

    with COMPOSITE_TRACER, NoTracing():
        space = StateSpace(time.monotonic() + 30.0, 3.0, search_root=search_root)
        with Patched(), StateSpaceContext(space):
            space.set_choice_hints([42])
            n = proxy_for_type(int, "n")
            with ResumedTracing():
                # The decision here is oracle-driven; we just want no crash.
                _ = bool(n > 10)
                space.detach_path()
        space.bubble_status(CallAnalysis(VerificationStatus.CONFIRMED))


def test_smt_fanout(space: SimpleStateSpace):
    option1 = z3.Bool("option1")
    option2 = z3.Bool("option2")
    space.add(z3.Xor(option1, option2))  # Ensure exactly one option can be set
    exprs_and_results = [(option1, "result1"), (option2, "result2")]

    result = space.smt_fanout(exprs_and_results, desc="choose_one")
    assert result in ("result1", "result2")
    if result == "result1":
        assert space.is_possible(option1)
        assert not space.is_possible(option2)
    else:
        assert not space.is_possible(option1)
        assert space.is_possible(option2)
