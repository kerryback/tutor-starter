import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from speech_text import SpeechStream, spoken_form


def run(chunks):
    s = SpeechStream(); out = []
    for c in chunks: out += s.feed(c)
    return out + s.flush()


def test_sentences_stream_out_as_they_complete():
    s = SpeechStream()
    assert s.feed("Here is a tree. The st") == ["Here is a tree."]
    assert s.feed("ock goes up.\n\nWhat is it worth?") == ["The stock goes up."]
    assert s.flush() == ["What is it worth?"]


def test_display_math_is_never_spoken_even_when_split():
    out = run(["Here is the formula for q.\n\n$", "$q = \\frac{1+r-d}{u-d}", "$", "$\n\nWhat is q?"])
    assert out == ["Here is the formula for q.", "What is q?"]


def test_tables_and_code_are_not_spoken():
    out = run(["Look at the table.\n| t | S |\n|---|---|\n| 0 | 100 |\n", "```\nx = 1\n```\nDone."])
    assert out == ["Look at the table.", "Done."]


def test_markdown_markers_and_inline_symbols_dropped():
    assert spoken_form("**Good.** Use `q = 0.6` here, and $C_u$ too.") == "Good. Use here, and too."
    assert spoken_form("## Step 1") == "Step 1"
    assert spoken_form("- first item") == "first item"
    assert spoken_form("$$x$$") == ""


def test_decimal_points_do_not_end_sentences():
    assert run(["q is 0.6 here. Next."]) == ["q is zero point six here.", "Next."]


def test_decimal_split_across_deltas():
    assert run(["q is 0.", "6 here. Next."]) == ["q is zero point six here.", "Next."]


def test_multiline_display_math_and_fence_skipped():
    out = run(["Before.\n$$\nq = 1\n$$\nAfter.\n``", "`py\nx = 1\n```\nEnd."])
    assert out == ["Before.", "After.", "End."]


def test_headings_and_list_items_go_on_the_board_not_into_speech():
    assert run(["1. Pick u.\n2. Pick d.\n"]) == []
    assert run(["## One-period call\nHere is the setup.\n- Strike K = 100\n- Up fac", "tor u = 1.1\n* Bond\nWhat is q?"]) == \
        ["Here is the setup.", "What is q?"]
    assert run(["The drop is -0.5 here."]) == ["The drop is minus zero point five here."]


def test_display_math_opening_mid_line_is_skipped():
    assert run(["The formula is $$", "\nq = 1+r", "\n$$\nDone."]) == ["The formula is", "Done."]
    assert run(["$$x$$ then say this."]) == ["then say this."]


def test_code_fence_opening_mid_line_is_skipped():
    assert run(["Run this ```", "\nx = 1\n```\nDone."]) == ["Run this", "Done."]


def test_inline_span_with_period_space_is_not_split():
    assert run(["Use $C_u = 1. 5$ ok. Next."]) == ["Use ok.", "Next."]
    assert run(["Use `a. b` ok. Next."]) == ["Use ok.", "Next."]
    assert run(["Use $C_u = 1.", " 5$ ok. Next."]) == ["Use ok.", "Next."]


def test_dollar_amounts_survive():
    assert spoken_form("Value $5 and $6 here.") == "Value $5 and $6 here."
    assert run(["Value $5 and $6 here. Then $C_u$ too."]) == ["Value $5 and $6 here.", "Then too."]
    assert spoken_form("Use $C_u$.") == "Use."


def test_stray_symbols_are_stripped():
    assert run(["Hi.\n$"]) == ["Hi."]
    assert spoken_form("a $ b ` c") == "a b c"


def test_inline_plain_text_formulas_are_not_spoken():
    # The formula is dropped; the comma after it stays: "So, which is ...".
    assert (spoken_form("So q = (1.02 - 0.9)/(1.1 - 0.9) = 0.6, which is the risk-neutral probability.")
            == "So, which is the risk-neutral probability.")
    assert spoken_form("The bond gives (1 + r) per dollar.") == "The bond gives per dollar."
    assert spoken_form("Exercise when S > K here.") == "Exercise when here."
    assert spoken_form("The payoff is max(S - K, 0) at expiry.") == "The payoff is at expiry."
    assert spoken_form("Then u^2 * S = 121 at the top.") == "Then at the top."
    assert spoken_form("q = 0.6.") == "q equals zero point six."   # a lone name = number is said
    assert spoken_form("Use n = 50.") == "Use n equals 50."


def test_prose_that_looks_like_symbols_survives():
    for s in ["Use a two-period tree.",
              "You can call and/or put.",
              "The payoff is $5 at the top.",
              "The up/down moves are fixed.",
              "Is the option in-the-money?",
              "See the tree (on the board) now."]:
        assert spoken_form(s) == s, s


def test_italic_markers_do_not_look_like_multiplication():
    assert spoken_form("Here *q* is the probability.") == "Here q is the probability."


def test_decimals_are_said_as_point_and_a_number():
    assert spoken_form("The value is 9.44 today.") == "The value is nine point forty-four today."
    assert spoken_form("The risk-neutral probability is 0.6.") == "The risk-neutral probability is zero point six."
    assert spoken_form("So q is 0.6 and u is 1.1.") == "So q is zero point six and u is one point one."
    assert spoken_form("R is 1.02.") == "R is one point oh two."
    assert spoken_form("Daily volatility is 0.0126.") == "Daily volatility is zero point zero one two six."
    assert spoken_form("u is 1.1618.") == "u is one point one six one eight."
    assert spoken_form("It costs $5.88 now.") == "It costs five point eighty-eight dollars now."
    assert spoken_form("The rate is 10% per year.") == "The rate is 10 percent per year."
    assert spoken_form("Rates of 2.5% apply.") == "Rates of two point five percent apply."
    assert spoken_form("A total of 1,234.50.") == "A total of one thousand two hundred thirty-four point fifty."
    assert spoken_form("Version 1.2.3 here.") == "Version 1.2.3 here."     # not a decimal


@pytest.mark.parametrize("prose,spoken", [
    ("Find: σ = 0.0126 × √252 = ?", ""),                          # a formula line: the board shows it
    ("What is σ = ?", ""),
    ("So q = 0.6, which is the probability.", "So q equals zero point six, which is the probability."),
    ("What changed between n = 3 and n = 50?", "What changed between n equals 3 and n equals 50?"),
    ("Multiply by √252 instead.", "Multiply by the square root of 252 instead."),
    ("Volatility σ is on the board.", "Volatility sigma is on the board."),
])
def test_formula_lines_and_symbols(prose, spoken):
    assert spoken_form(prose) == spoken


def test_symbols_run_together_are_spoken_as_separate_words():
    assert spoken_form("The volatility per period is σ√Δt, by the same rule.") == \
        "The volatility per period is sigma the square root of delta t, by the same rule."
