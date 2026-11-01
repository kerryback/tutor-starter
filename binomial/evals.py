"""The binomial tutor's eval scenarios.  Run them with scripts/eval.sh binomial."""

import re

from harness import (ends_on_question, ends_on_request, mentions_number, play,  # noqa: F401
                     scenario, seen_and_heard, tool_calls, BANNED_IN_SPEECH)
from topic import _solve


def hidden_values(tree_payload, inputs):
    sol = _solve(inputs)
    return [sol["value"][nd["t"]][nd["i"]] for nd in tree_payload["nodes"] if nd["V"] is None]


@scenario
async def diagnose(tutor, student):
    turns = await play(tutor, student, [
        None,
        "I've seen this before. I have a problem I want checked: S = 100, next period it is 110 "
        "or 90, r = 2% per period, a call struck at 100. I got 4.90. Is that right?",
    ])
    t = turns[-1]["tutor"]
    names = [c[0] for c in tool_calls(student)]
    return turns, {
        "does not reveal 5.88": not mentions_number(seen_and_heard(turns[-1]), 5.8824),
        "says it is not right": re.search(r"\b(not|isn't|no)\b", t, re.I) is not None,
        "asks about the 0.5": "0.5" in t or "50%" in t or "probab" in t.lower() or "weight" in t.lower(),
        "graded with a tool": "check_answer" in names or "price_tree" in names,
        "ends on a question or a request": ends_on_request(t),
    }


@scenario
async def exercise_then_ask_for_answer(tutor, student):
    turns = await play(tutor, student, [
        None,
        "I know one-period trees. Give me a two-period tree to fill in.",
        "I'm lost. Just tell me the answer.",
    ])
    shown = [tr for t in turns for tr in t["trees"]]
    checks = {"showed a tree": bool(shown)}
    blanked = [tr for tr in shown if any(nd["V"] is None for nd in tr["nodes"])]
    checks["the tree has blanks"] = bool(blanked)
    checks["problem turn ends on the request"] = ends_on_request(turns[1]["tutor"])
    checks["no tree typed into the chat"] = all("```" not in t["tutor"] for t in turns)
    if blanked:
        tree = blanked[0]
        inputs = student["conversation"]["trees"][tree["id"]]
        secret = hidden_values(tree, inputs)
        checks["problem turn leaks no hidden value"] = not any(
            mentions_number(seen_and_heard(turns[1]), v) for v in secret)
        checks["first 'tell me' gets a worked example, not the answer"] = not any(
            mentions_number(seen_and_heard(turns[2]), v) for v in secret)
    return turns, checks


@scenario
async def resume(tutor, student):
    student["progress"] = {"modules_done": [1, 2], "now_in": "3, stopped after exercise 3.1",
                           "mistakes_seen": ["forgot to discount (twice)"], "notes": ""}
    tutor.ensure_conversation(student, fresh=True)
    turns = await play(tutor, student, [None])
    t = turns[0]["tutor"]
    return turns, {
        "names where the student stopped": re.search(
            r"(module\s*(3|three)|3\.1|three point one|two-period)", t, re.I) is not None,
        "asks whether to pick up there": ends_on_question(t),
    }


@scenario
async def voice_board(tutor, student):
    turns = await play(tutor, student, [None, "How do I compute q?"])
    t = turns[-1]
    return turns, {
        "reply has a $$ block": re.search(r"\$\$.+?\$\$", t["tutor"], re.S) is not None,
        "no spoken sentence has = \\ ^ _ $ or ***": not any(BANNED_IN_SPEECH.search(x) for x in t["spoken"]),
        "something was spoken": bool(t["spoken"]),
        "no ** in the reply": "**" not in t["tutor"],
    }


@scenario
async def calibration(tutor, student):
    """Module 3, section 6: estimate volatility, the CRR rule, and why log
    returns become normal, with the return_distribution plot."""
    turns = await play(tutor, student, [
        None,
        "I know multi-period trees already. Teach me how to fit a tree to a stock's volatility.",
        "I'd take the standard deviation of daily returns and multiply it by 252.",
        "Oh, the square root of 252 then. That gives about 0.20.",
        "OK. So what is the rule for u and d? Just tell me the formula.",
        "Sigma squared times delta t.",
        "Why does the return become normal when there are lots of periods?",
        "The central limit theorem?",
        "Can you show me a picture of that?",
    ])
    calls = tool_calls(student)
    trap = turns[2]["tutor"].lower()
    after_trap = re.sub(r"^#.*$", "", trap, flags=re.M).strip()
    later = " ".join(seen_and_heard(t) for t in turns[4:])
    plots_drawn = [c[1] for c in calls if c[0] == "show_plot" and c[1].get("plot") == "return_distribution"]
    return turns, {
        "does not accept times 252": not re.match(r"(right|correct|exactly|yes|good|great)\b", after_trap),
        "challenges the 318%": "318" in trap or "believ" in trap or "square root" in trap,
        "gives the CRR rule (sqrt of Δt in the exponent)": re.search(
            r"σ\s*√\s*\(?\s*Δt|\\sigma\s*\\sqrt\{\s*\\Delta\s*t\s*\}|σ\s*\\sqrt", later) is not None,
        "d = 1/u": re.search(r"d\s*=\s*(1\s*/\s*u|\\frac\{1\}\{u\}|u\^\{-1\})", later) is not None,
        "says the limit is normal": "normal" in " ".join(seen_and_heard(t) for t in turns[7:]).lower(),
        "draws the return_distribution plot": bool(plots_drawn),
        "used calculate or a tree tool": any(c[0] in ("calculate", "price_tree", "show_tree") for c in calls),
        "ends each turn on a request": all(ends_on_request(t["tutor"]) for t in turns[1:]),
    }


@scenario
async def nearby_question(tutor, student):
    """A neighboring topic, Black-Scholes, in the middle of Module 1: a short answer, then back to the lesson."""
    turns = await play(tutor, student, [
        None,
        "Start from the beginning, please. I haven't seen this before.",
        "Quick question: how does this relate to Black-Scholes?",
    ])
    t = turns[-1]["tutor"]
    heard = seen_and_heard(turns[-1])
    return turns, {
        "answers it": re.search(r"limit|many (?:periods|steps)|more (?:periods|steps)|converge", heard, re.I) is not None,
        "briefly (under 150 words)": len(t.split()) < 150,
        "ends on a question or a request": ends_on_request(t),
    }
