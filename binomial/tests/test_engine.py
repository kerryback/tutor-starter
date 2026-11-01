import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import binomial as bt  # noqa: E402

# (S, K, r, u, d, n, kind, price) from content/exercises.md
BANK = [
    (80, 80, .03, 1.25, .8, 1, "European call", 9.92),
    (100, 105, .02, 1.2, .85, 2, "European call", 8.84),
    (40, 42, .04, 1.2, .85, 2, "European put", 3.08),
    (25, 25, .01, 1.1, 1 / 1.1, 3, "European call", 2.14),
    (100, 110, .05, 1.15, .85, 2, "American put", 10.41),
    (100, 110, .05, 1.15, .85, 2, "European put", 8.74),
    (60, 60, .03, 1.15, .9, 3, "American put", 3.38),
    (50, 50, .01, 1.1, 1 / 1.1, 3, "American call", 4.29),
    (200, 210, .04, 1.1, .95, 1, "American put", 10.00),
    (100, 100, .05, 1.25, .8, 1, "European call", 13.23),
]


@pytest.mark.parametrize("S,K,r,u,d,n,kind,price", BANK)
def test_problem_bank(S, K, r, u, d, n, kind, price):
    assert round(bt.solve(S, K, r, u, d, n, kind)["value"][0][0], 2) == price


def test_put_call_parity():
    c = bt.solve(100, 105, .02, 1.2, .85, 2, "call")["value"][0][0]
    p = bt.solve(100, 105, .02, 1.2, .85, 2, "put")["value"][0][0]
    assert abs((c - p) - (100 - 105 / 1.02 ** 2)) < 1e-9


def test_american_call_equals_european():
    a = bt.solve(50, 50, .01, 1.1, 1 / 1.1, 3, "American call")
    e = bt.solve(50, 50, .01, 1.1, 1 / 1.1, 3, "European call")
    assert abs(a["value"][0][0] - e["value"][0][0]) < 1e-12 and not a["exercise"]


def test_no_arbitrage_refused():
    with pytest.raises(ValueError, match="No-arbitrage"):
        bt.solve(100, 100, .12, 1.1, .9, 1, "call")


@pytest.mark.parametrize("kind,expected", [
    ("American put", ("american", "put")), ("american-put", ("american", "put")),
    ("European_call", ("european", "call")), ("put", ("european", "put")),
])
def test_parse_kind(kind, expected):
    assert bt.parse_kind(kind) == expected


@pytest.mark.parametrize("spec,expected", [
    ("0", (0, 0)), ("u", (1, 0)), ("d", (1, 1)), ("ud", (2, 1)), ("du", (2, 1)), ("2,2", (2, 2)),
])
def test_parse_node(spec, expected):
    assert bt.parse_node(spec, 3) == expected


def test_parse_node_out_of_tree():
    with pytest.raises(ValueError):
        bt.parse_node("uuu", 2)


def test_hidden_nodes_include_ancestors():
    assert bt.hidden_nodes((2, 1), 3) == {(2, 1), (1, 0), (1, 1), (0, 0)}


# The diagnostic table in the protocol, for the running one-period example.
SIGNATURES = [
    (5.88, True, []), (6.00, False, ["no_discount"]), (4.90, False, ["real_prob_half"]),
    (3.92, False, ["flipped_q", "other_right"]), (5.00, False, ["average_payoffs"]),
    (9.80, False, ["up_only"]), (0.50, False, ["gave_delta"]), (50.00, False, ["delta_times_S"]),
]


@pytest.mark.parametrize("answer,correct,matches", SIGNATURES)
def test_signatures(answer, correct, matches):
    sol = bt.solve(100, 100, .02, 1.1, .9, 1, "European call")
    res = bt.check(sol, "0", answer)
    assert res["correct"] is correct and sorted(res["matches"]) == sorted(matches)


def test_american_forgot_exercise_today():
    # exercise 4.2: holding is worth 7.69 but exercising pays 10
    sol = bt.solve(200, 210, .04, 1.1, .95, 1, "American put")
    assert "forgot_exercise_here" in bt.check(sol, "0", 7.69)["matches"]


def test_multiperiod_discount_once():
    sol = bt.solve(100, 105, .02, 1.2, .85, 2, "European call")
    q = sol["q"]
    exp_T = q * q * 39
    assert "discount_once" in bt.check(sol, "0", exp_T / 1.02)["matches"]
    assert "no_discount_multi" in bt.check(sol, "0", exp_T)["matches"]


def test_check_delta_bond_q():
    sol = bt.solve(80, 80, .03, 1.25, .8, 1, "European call")
    assert bt.check(sol, "0", 0.5556, "delta")["correct"]
    assert bt.check(sol, "0", -34.52, "bond")["correct"]
    assert "bond_sign" in bt.check(sol, "0", 34.52, "bond")["matches"]
    assert "q_flipped" in bt.check(sol, "0", 1 - sol["q"], "q")["matches"]


def test_textbook_conversion():
    conv = bt.from_textbook(rate=0.05, sigma=0.3, T=1, n=4)
    assert abs(conv["r"] - 0.0125785) < 1e-6 and abs(conv["u"] * conv["d"] - 1) < 1e-12
