"""Pure-logic tests for FDM Iran reachability (check-host.net verdicts)."""

from app.services.fdm.iran_reach import (
    BLOCKED,
    INCONCLUSIVE,
    REACHABLE,
    classify,
    is_iran_blocked,
    next_blocked_streak,
    pick_check_port,
)

IR = ["ir1", "ir2", "ir3", "ir4", "ir5", "ir7"]
CTRL = "de1"
OK = [{"address": "1.2.3.4", "time": 0.2}]
TIMEOUT = [{"error": "Connection timed out"}]


def _full(node):
    return f"{node}.node.check-host.net"


def _result(ir_values, ctrl_value):
    res = {_full(n): v for n, v in zip(IR, ir_values)}
    res[_full(CTRL)] = ctrl_value
    return res


def _classify(res, min_nodes=4):
    return classify(res, IR, CTRL, min_nodes)


def test_all_iran_nodes_time_out_with_control_ok_is_blocked():
    assert _classify(_result([TIMEOUT] * 6, OK)) == BLOCKED


def test_all_iran_nodes_connect_is_reachable():
    assert _classify(_result([OK] * 6, OK)) == REACHABLE


def test_one_iran_node_failing_is_still_reachable():
    assert _classify(_result([OK] * 5 + [TIMEOUT], OK)) == REACHABLE


def test_iran_failures_with_control_failing_is_inconclusive():
    # Dead from everywhere: a node outage, not Iranian filtering.
    assert _classify(_result([TIMEOUT] * 6, TIMEOUT)) == INCONCLUSIVE


def test_pending_control_is_inconclusive():
    assert _classify(_result([TIMEOUT] * 6, None)) == INCONCLUSIVE


def test_too_few_iran_answers_is_inconclusive():
    # Only 3 Iranian nodes answered (all failed), below min_nodes=4.
    res = _result([TIMEOUT] * 3 + [None] * 3, OK)
    assert _classify(res) == INCONCLUSIVE


def test_even_split_is_inconclusive():
    res = _result([OK] * 3 + [TIMEOUT] * 3, OK)
    assert _classify(res) == INCONCLUSIVE


def test_majority_of_answering_nodes_failing_is_blocked():
    res = _result([TIMEOUT] * 4 + [OK] + [None], OK)
    assert _classify(res) == BLOCKED


def test_missing_or_malformed_result_is_inconclusive():
    assert _classify({}) == INCONCLUSIVE
    assert _classify(None) == INCONCLUSIVE
    assert _classify(_result(["garbage"] * 6, "garbage")) == INCONCLUSIVE


def test_blocked_streak_counts_up_resets_and_holds():
    assert next_blocked_streak(0, BLOCKED) == 1
    assert next_blocked_streak(1, BLOCKED) == 2
    assert next_blocked_streak(5, REACHABLE) == 0
    assert next_blocked_streak(1, INCONCLUSIVE) == 1  # missing data never moves it
    assert next_blocked_streak(None, BLOCKED) == 1


def test_is_iran_blocked_threshold():
    assert not is_iran_blocked(1, 2)
    assert is_iran_blocked(2, 2)


def test_pick_check_port_prefers_vless_then_trojan_then_any():
    assert pick_check_port({"ss": 1, "vless": 2, "trojan": 3}) == 2
    assert pick_check_port({"ss": 1, "trojan": "3"}) == 3
    assert pick_check_port({"ss": "1"}) == 1
    assert pick_check_port({}) is None
    assert pick_check_port(None) is None
    assert pick_check_port({"vless": "bad"}) is None
