"""The eval harness's board checks (evals/harness.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "evals"))
import harness  # noqa: E402


def _turn(tutor, plots=()):
    return {"tutor": tutor, "trees": [], "plots": list(plots)}


def test_a_number_said_but_not_shown_fails():
    assert not harness.numbers_on_board([_turn("## Setup\n\nAlpha is 5%.\n\n- Beta = 1.2")])


def test_a_number_in_a_plot_caption_counts_as_shown():
    plot = {"data": [], "layout": {}, "caption": "Baseline: alpha 5%, idiosyncratic sd 24%"}
    assert harness.numbers_on_board([_turn("## Setup\n\nAlpha is 5% and the sd is 24%.", [plot])])


def test_years_and_index_names_need_not_be_on_the_board():
    text = ("## Setup\n\nWe use monthly returns from January 2006 to December 2025, or 2006-01 to 2025-12, "
            "on a Treasury ETF and an S&P 500 ETF.\n\n- Funds: IEF, SPY")
    assert harness.numbers_on_board([_turn(text)])


def test_a_result_referred_back_to_must_be_on_the_board():
    assert not harness.numbers_on_board([_turn("## Three funds\n\nEarlier the weight was 46.9% in SPY.")])


def test_a_year_at_the_end_of_a_sentence_is_exempt():
    assert harness.numbers_on_board([_turn("## Data\n\nReturns run from 2006 to 2025. Data through August 2026.")])


def test_labels_like_fund_1_are_exempt():
    assert harness.numbers_on_board([_turn("## Weights\n\nFor fund 1 and fund 2, and asset 2, the scores differ.")])


def test_s_and_p_in_words_is_exempt():
    assert harness.numbers_on_board([_turn("## Funds\n\nSPY, the S and P 500 fund.")])
