# Module 3 — Many periods and calibration

Goal: the student should see that nothing new happens after Module 1. A
multi-period tree is a one-period tree glued to itself, and backward induction is
the glue.

Then the module answers where u and d come from: the student fits a tree to an
estimated volatility by the Cox-Ross-Rubinstein rule, and sees why the log
return becomes normal as the number of periods grows (section 6).

## 1. Ask before you show

Extend the running example to two periods: from 110 the stock goes to 121 or 99;
from 90 it goes to 99 or 81. Same 2% per period, same strike of 100.

```
        t=0                t=1                t=2
---------------------------------------------------------
                                        121.00
                     110.00
  100.00                                 99.00
                      90.00
                                         81.00
```

Ask two questions before teaching anything, and wait for both:

1. Why is there one node at 99 instead of two? (Up-then-down and
   down-then-up land in the same place, because `u·d = d·u`. The tree
   recombines. This is worth flagging now because it is what makes large trees
   computable.)
2. We know how to price an option that expires next period. Here the option has
   two periods to go. Where could we stand in this tree such that the problem
   looks like the one we already solved?

Question 2 is the module. If the student says "at date 1," they have discovered
backward induction and the rest is arithmetic. If they don't, narrow it: "suppose
it's date 1 and the stock is at 110 — how many periods are left?"

## 2. Work backward

Terminal payoffs first — ask for them: 21, 0, 0.

Now the up node at date 1. The stock is at 110 and goes to 121 or 99. That is
exactly a one-period problem, and `q = 0.6` still, because q depends only on u,
d, and r:

```
C_u = (0.6 · 21 + 0.4 · 0)/1.02 = 12.35
```

Ask for the down node yourself before giving it (0, since the option is worthless
in both successor states). Then date 0, treating the date-1 values as the
payoffs:

```
C_0 = (0.6 · 12.35 + 0.4 · 0)/1.02 = 7.27
```

```
        t=0                t=1                t=2
---------------------------------------------------------
                                        121.00 /   21.00
                     110.00 /   12.35
  100.00 /    7.27                       99.00 /    0.00
                      90.00 /    0.00
                                         81.00 /    0.00
```

The step students skip past: at date 0 we discounted 12.35, which is not a cash
flow. Nobody receives 12.35. Ask why we may treat it as one. (Because it is the
market value of the option at that node — you could sell it for exactly that,
and a value you can convert to cash is as good as cash.)

## 3. The hedge is dynamic — this is the real content

Most students take backward induction on faith. Don't let them; the replication
argument still has to work, and seeing it work is what makes multi-period pricing
believable.

At date 0, `Δ = (12.35 − 0)/(110 − 90) = 0.6176` and `B = 7.27 − 0.6176·100 =
−54.50`.

Now the question to ask, and it is the good one:

> Hold that portfolio for one period. If the stock goes up to 110, what is it
> worth?

```
0.6176 · 110 − 54.50 · 1.02 = 67.94 − 55.59 = 12.35
```

Exactly `C_u`. And in the down state it is worth exactly 0. So the date-0
portfolio, left alone, always turns into precisely enough to fund the date-1
portfolio — no money added, none taken out. That property is called
self-financing, and it is what licenses the whole recursion: the option is
replicated not by one static portfolio but by a trading strategy that rebalances
at each node.

Have them compute the new delta at the up node: `(21 − 0)/(121 − 99) = 0.9545`.
The hedge got heavier as the option moved into the money. That is delta hedging,
and the student has now done it.

```
python scripts/binomial.py --S 100 --K 100 --r 0.02 --u 1.1 --d 0.9 --n 2 \
    --kind "European call"
```

The `delta` and `bond` columns let them check the self-financing property at
every node.

## 4. Fill in the node

Give them this and stop:

```
        t=0                t=1                t=2
---------------------------------------------------------
                                         57.60 /    0.00
                      48.00 /    0.53
   40.00 /       ?                       40.80 /    1.20
                      34.00 /       ?
                                         28.90 /   13.10

  European put, S = 40, K = 42, r = 4% per period, u = 1.20, d = 0.85
```

Answers: `q = (1.04 − 0.85)/(1.20 − 0.85) = 0.5429`; down node
`(0.5429·1.20 + 0.4571·13.10)/1.04 = 6.38`; price
`(0.5429·0.53 + 0.4571·6.38)/1.04 = 3.08`.

Generate more of these — see `references/exercises.md`, or:

```
python scripts/binomial.py --S 40 --K 42 --r 0.04 --u 1.2 --d 0.85 --n 2 \
    --kind "European put" --blank d
```

A worthwhile follow-up on this particular tree: the exercise value at the date-1
down node is 42 − 34 = 8, which is more than the 6.38 we just computed. Ask what
that means. It means nothing yet for a European put — the holder cannot act on it
— and it is the entire subject of Module 4. This is a good place to end if the
student wants a break.

## 5. n periods

Two moves generalize the recursion; ask the student to supply both.

Number of nodes. At date t there are t+1 nodes, not 2^t, because the tree
recombines. Ask them to count paths versus nodes at date 3: eight paths, four
nodes. A 50-period tree has 2^50 paths — about a quadrillion — and 51 nodes.
That gap is why this model is practical.

The recursion. At every node with time left,

```
V = [ q·V_up + (1 − q)·V_down ] / (1 + r)
```

applied from the terminal date backward. No new idea; the same one-period
argument at every node, with a self-financing strategy that rebalances each
period.

For a European option only, the recursion collapses into a formula, because a
node at date n with k up moves is reached by C(n,k) paths each of q-probability
`q^k (1−q)^(n−k)`:

```
C_0 = (1 + r)^(−n) · Σ_k C(n,k) · q^k (1 − q)^(n−k) · max(S·u^k·d^(n−k) − K, 0)
```

Check it against the two-period answer: only k = 2 pays, so
`0.36 · 21/1.02² = 7.27`. Same number. Emphasize why this shortcut exists only
for European options: it assumes we never do anything before the terminal date.
Module 4 breaks that assumption, and the formula goes with it.

## 6. Calibration: fitting the tree to volatility

Teach this after section 5. Until now u and d were given. Real options do not
come with a tree: they come with a time to maturity, an interest rate, and an
estimate of the stock's volatility. The periods are not economically
meaningful. They slice a fixed time T into n pieces, and u and d are chosen so
that the tree's returns have the volatility we estimated.

### Estimating volatility

Volatility σ is the standard deviation of the stock's continuously compounded
return over one year. The continuously compounded (log) return over a period
is `log(S_end / S_start)`.

Ask how they would estimate σ from price data. Most students get to "the
standard deviation of past returns" and need help with two details:

1. Use log returns, `log(S_t / S_{t−1})`, one for each day.
2. Annualize. Returns on separate days are roughly independent, so variances
   add: the variance over a year is 252 times the daily variance (252 trading
   days), and the standard deviation is `√252` times the daily one.

```
σ = (standard deviation of daily log returns) × √252
```

Example: a daily standard deviation of 1.26% gives `σ = 0.0126 × √252 = 0.20`.

The trap to set: ask for the annual figure before showing the rule. A student
who multiplies by 252 gets 3.18, a volatility of 318%, and should be asked
whether that is believable. Variances scale with time; standard deviations
scale with its square root. The same rule carries the volatility from a year
down to one period of the tree.

Only if asked: traders often use implied volatility instead, the σ that makes
a model price match a market price. Calibration works the same way with either.

### What the tree must match

With T years and n periods, each period is `Δt = T/n` years. Over one period
the log return is either `log u` or `log d`, so under q its variance is

```
q(1 − q)(log u − log d)²
```

That should equal `σ²Δt`, the variance of a log return over Δt. Ask the student
for `σ²Δt` before showing the formula: it is the scaling rule again.

The mean matters too. In the continuous-time model the risk-neutral mean of the
log return over a period is `(rate − σ²/2)Δt`, where `rate` is the annual
continuously compounded rate. Do not derive the −σ²/2 term. Say that it is the
gap between the average log return and the log of the average return.
Getting the variance right matters most; the mean comes right as Δt shrinks.

### The Cox-Ross-Rubinstein rule

```
Δt = T/n        u = e^(σ√Δt)        d = 1/u        1 + r = e^(rate·Δt)

q = (1 + r − d) / (u − d)
```

`d = 1/u` makes an up move and a down move cancel, so the tree recombines at
the starting price. `u = e^(σ√Δt)` makes the log return each period
`+σ√Δt` or `−σ√Δt`. q comes from the per-period rate exactly as in Module 2.

Check the variance with the student: `(log u − log d)² = 4σ²Δt`, so the
variance per period is `4q(1 − q)σ²Δt`. That is exactly `σ²Δt` when q = 1/2,
and q goes to 1/2 as Δt shrinks. For σ = 0.3, a 5% rate and T = 1:

```
   n      u          d          q        mean/Δt    variance/Δt
   1   1.349859   0.740818   0.509741   0.005845    0.089966
   4   1.161834   0.860708   0.504342   0.005210    0.089993
  12   1.090463   0.917042   0.502439   0.005070    0.089998
 100   1.030455   0.970446   0.500835   0.005008    0.090000
```

The variance per year is σ² = 0.09 to four places at every n, and the mean per
year approaches `rate − σ²/2 = 0.005`. Point out what happens to u and d: they
move toward 1. More periods do not mean a more volatile stock. Each step is
smaller and there are more of them, so the volatility over the year stays σ.

### Worked example — a calibrated tree

S = 100, K = 100, European call, σ = 0.3, rate 5% a year continuously
compounded, T = 1 year, n = 4 periods. Ask for each parameter before giving it,
and get each from `calculate`:

- Δt = 1/4 = 0.25
- u = e^(0.3 × √0.25) = e^0.15 = 1.1618
- d = 1/u = 0.8607
- 1 + r = e^(0.05 × 0.25) = 1.0126, so r = 1.26% per period
- q = (1.0126 − 0.8607)/(1.1618 − 0.8607) = 0.5043

Then draw the tree with `show_tree`, passing `sigma`, `rate` and `T` (the tools
apply the same rule), and ask for one node the usual way. The call is worth
13.52. With n = 12 it is worth 13.99. The price changes with n because a finer
tree is a better approximation, not because the stock changed. Once the
parameters are set, the pricing is sections 2 to 5 unchanged.

### Why returns become normal

This is the idea the section builds to. Ask the student to describe the log
return over the whole T years. They have the pieces:

- It is the sum of n per-period log returns.
- Each is `+σ√Δt` or `−σ√Δt`, independently of the others.
- With k up moves, `log(S_T / S) = (2k − n)σ√Δt`, and k is binomial.

So the log return over T is a sum of many small, independent, identically
distributed pieces. Ask which theorem says what such a sum looks like: the
central limit theorem. As n grows with T fixed, the distribution approaches a
normal distribution, with mean `(rate − σ²/2)T` and variance `σ²T`.

```
log(S_T / S)  →  normal, mean (rate − σ²/2)T, variance σ²T
```

Show it with `show_plot` and the `return_distribution` plot: bars for the
tree's probability of each possible log return, and a curve for the normal
limit. Plot n = 3, then n = 50, with the same σ, rate and T, and ask what
changed. Three periods give four possible returns and a poor fit; fifty give
bars that follow the curve.

Then the consequence: if `log S_T` is normal, `S_T` is lognormal. It can rise
without limit but never falls below zero. That is the distribution the
Black-Scholes model assumes, so the European price on a calibrated tree
converges to the Black-Scholes price (14.23 in the worked example) as n grows.
The binomial model is not an approximation to reality that Black-Scholes
improves on; they are the same model at different resolutions. Say this in a
sentence or two and do not develop Black-Scholes.

### Exercise — calibrate and price

Give it and stop:

```
Daily log returns: standard deviation 1.26%
S = 40, K = 40, European call
Rate 3% a year, continuously compounded
T = 1 year, n = 3 periods
```

Answers: σ = 0.0126 × √252 = 0.20, Δt = 1/3, u = e^(0.2 × √(1/3)) = 1.1224,
d = 0.8909, 1 + r = e^0.01 = 1.0101, q = 0.5146, call value 4.02. Grade each
parameter with `calculate`, and the price with `check_answer` on a tree drawn
with `sigma`, `rate` and `T`. For a fast student, the American put on the same
tree is worth 2.93; save it for Module 4.

### Where students get stuck on calibration

Using σ for each period instead of `σ√Δt`. A student who sets u = e^0.2 on a
three-period tree has given the stock a volatility of 0.2 every period, so
√3 × 0.2 = 0.35 over the year. Ask what the volatility over one period should
be.

Scaling volatility by time instead of its square root. Ask whether 318% is
believable.

Mixing up the rates. The tree's r is per period: `e^(rate·Δt) − 1`. Using the
annual rate in every period, or `rate·Δt` without the exponential, gives a
wrong q. The second error is small; `check_answer` catches it.

Simple returns versus log returns. Volatility is defined for log returns, and
only log returns add across periods. The normal limit is for the log return,
not for `S_T/S − 1`.

Next: `references/04-american.md`.
