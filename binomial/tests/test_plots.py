import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import plots  # noqa: E402
from test_voice_tutor import FakeClient, student, tool_block  # noqa: E402
from tools import ToolError, run_tool  # noqa: E402
from tutor import Store, Tutor  # noqa: E402


def st():
    return {"trees": {}, "progress": None}


def test_payoff_plot_values():
    f = plots.payoff("call", 100)
    xs, ys = f["data"][0]["x"], f["data"][0]["y"]
    assert xs[0] == 0 and xs[-1] == 200 and ys[0] == 0 and ys[-1] == 100
    short_put = plots.payoff("put", 100, "short")["data"][0]["y"]
    assert short_put[0] == -100 and short_put[-1] == 0


def test_american_put_is_never_below_european_or_exercise_value():
    f = plots.american_vs_european(100, 0.02, 1.1, 0.9, 3)
    amer, euro, exer = (t["y"] for t in f["data"])
    assert all(a >= e - 1e-9 and a >= x - 1e-9 for a, e, x in zip(amer, euro, exer))
    assert f["layout"]["annotations"][0]["text"] == "exercise early"
    assert f["layout"]["shapes"][0]["x1"] < 100        # early exercise only deep in the money


def test_show_plot_tool():
    text, payload = run_tool("show_plot", {"plot": "payoff", "kind": "put", "K": 90, "caption": "A put"}, st())
    assert "payoff at expiry of a long put with strike 90" in text
    assert payload["plot"]["caption"] == "A put" and payload["plot"]["data"]
    text, payload = run_tool("show_plot", {"plot": "american_vs_european", "K": 100, "n": 4,
                                           "rate": 0.05, "sigma": 0.3, "T": 1}, st())
    assert "n=4" in text and len(payload["plot"]["data"]) == 3


def test_return_distribution_is_a_density_that_approaches_the_normal():
    for n in (3, 50):
        f = plots.return_distribution(0.3, 0.05, 1, n)
        bars, curve = f["data"]
        width = 2 * 0.3 * (1 / n) ** 0.5
        assert abs(sum(bars["y"]) * width - 1) < 1e-3           # bar areas sum to one
        mean = sum(x * y * width for x, y in zip(bars["x"], bars["y"]))
        assert abs(mean - (0.05 - 0.045)) < 0.01
    assert len(plots.return_distribution(0.3, 0.05, 1, 3)["data"][0]["x"]) == 4
    peak = max(plots.return_distribution(0.3, 0.05, 1, 50)["data"][1]["y"])
    assert abs(peak - 1 / (0.3 * (2 * 3.141592653589793) ** 0.5)) < 1e-3


def test_return_distribution_tool():
    text, payload = run_tool("show_plot", {"plot": "return_distribution", "sigma": 0.3, "rate": 0.05,
                                           "T": 1, "n": 50}, st())
    assert "50-period tree" in text and "mean 0.005" in text and len(payload["plot"]["data"]) == 2


@pytest.mark.parametrize("args", [
    {"plot": "return_distribution", "sigma": 0.3, "rate": 0.05, "T": 1},                 # no n
    {"plot": "return_distribution", "sigma": 0.3, "rate": 0.05, "T": 1, "n": 500},
    {"plot": "return_distribution", "sigma": 0.01, "rate": 0.5, "T": 1, "n": 2},         # q above 1
    {"plot": "payoff", "kind": "call"},                                                  # no K
    {"plot": "payoff", "kind": "swap", "K": 100},
    {"plot": "payoff", "kind": "call", "K": -5},
    {"plot": "american_vs_european", "K": 100, "r": 0.02, "u": 1.1, "d": 0.9},          # no n
    {"plot": "american_vs_european", "K": 100, "n": 3, "r": 0.2, "u": 1.1, "d": 0.9},   # arbitrage
    {"plot": "convergence", "K": 100},
])
def test_show_plot_refuses_bad_input(args):
    with pytest.raises(ToolError):
        run_tool("show_plot", args, st())


def test_tutor_puts_the_plot_on_the_board(tmp_path):
    steps = [(["Here is what a call pays.\n\n"], [tool_block("show_plot", {"plot": "payoff", "kind": "call", "K": 100})], "tool_use"),
             (["What does it pay if the stock ends at one hundred twenty?"], [], "end_turn")]
    tutor = Tutor(Store(tmp_path), client=FakeClient(steps), voice=True)
    s = student()

    async def go():
        return [e async for e in tutor.turn(s, "hi")]

    evs = asyncio.run(go())
    plot = [e for e in evs if e["type"] == "plot"]
    assert len(plot) == 1 and plot[0]["plot"]["data"][0]["y"][-1] == 100
    roles = [d["role"] for d in s["conversation"]["display"]]
    assert roles == ["student", "tutor", "plot", "tutor"]
