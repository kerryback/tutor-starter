# Module 1 — One period: replication and no arbitrage

Goal: the student should be able to say why an option has exactly one possible
price, and compute it, without ever mentioning a probability.

Teach it in this order. In each part, teach the idea and work the example
yourself first, then give the student the practice example and wait.

## 1. Set up the tree

Teach: give the numbers and draw the stock tree. Running example:

- Stock is at 100. In one period it is either 110 or 90.
- Risk-free rate is 2% per period, so a dollar in the bond becomes 1.02.
- Price a call with strike 100.

```
        t=0                t=1
--------------------------------------
                     110.00
  100.00
                      90.00
```

Say what the call pays in each state: 110 − 100 = 10 in the up state, and 0 in
the down state, where the holder lets it expire.

Practice: same tree, a call with strike 95. What does it pay in each state?
(15 and 0.) It is easy on purpose.

## 2. Build the portfolio

Teach: now the move that carries everything. We build a portfolio of stock and
bond that pays 10 in the up state and 0 in the down state.

Let the portfolio hold `Δ` shares and `B` dollars in the bond. Its date-1 value
is `Δ·110 + 1.02B` up and `Δ·90 + 1.02B` down. Set those equal to 10 and 0.

Subtract one equation from the other. Say that this step is the whole idea:

```
Δ(110 − 90) = 10 − 0     so     Δ = (10 − 0)/(110 − 90) = 0.5
```

Delta is the ratio of the option's spread to the stock's spread — how much stock
it takes to match the option's sensitivity. Then from the down equation,
`0.5·90 + 1.02B = 0`, so `B = −45/1.02 = −44.12`. The portfolio is half a share
financed partly by borrowing 44.12.

Practice: replicate the strike-95 call from part 1. What are Δ and B?
(Δ = 15/20 = 0.75, B = −0.75·90/1.02 = −66.18.)

## 3. Price it

Teach: the portfolio costs `0.5 · 100 − 44.12 = 5.88` today.

Then the argument, which is worth saying slowly: the portfolio and the option
have identical payoffs in every state the world can reach. Two things with the
same payoff must have the same price, or you buy the cheap one, sell the dear
one, and pocket the difference today with nothing owed later. So the call is
worth 5.88. Not approximately, not on average — exactly, or there is free money
on the table.

Work one arbitrage: suppose the call is quoted at 6.50. Sell the call, buy the
portfolio, and keep 0.62 today. At date 1 the portfolio pays exactly what you
owe on the call in both states, so the position nets to zero.

Practice: what does the strike-95 call cost? (0.75 · 100 − 66.18 = 8.82.) Then:
it is quoted at 8.00. What do you do? (Buy the call, short 0.75 shares, lend
66.18, and keep 0.82 today; the position nets to zero at date 1.) Let them
construct it. Students believe the no-arbitrage argument only after they have
personally taken money out of it.

## 4. The punchline

Teach: this is what makes the module worth doing. Say it and let it land:

> Nothing in that calculation used the probability that the stock goes up. Not
> 50%, not 60%, nothing. The price of a bet on the stock does not depend on how
> likely the stock is to rise.

Then say why: the hedge works in both states, so we never had to weigh them.
Two investors who disagree completely about the stock's prospects still agree
that half a share minus 44.12 of borrowing replicates the call, and so they
agree on 5.88. The probability is already inside the stock price of 100 — the
option is priced relative to the stock, and the disagreement has nowhere left
to enter.

This is the sentence students should leave with: the option is priced relative
to the stock, not from a forecast about the stock.

Practice: one investor thinks the stock goes up with probability 30%, another
with 90%. What does each say the strike-95 call is worth? (8.82, both.) Then ask
which line of their calculation would change if the probability changed. (None.)

## 5. Check understanding

Offer one, and ask which they'd like:

(a) Same tree, price the put with strike 100.
Answer: Δ = (0 − 10)/(110 − 90) = −0.5, B = +53.92, price 3.92. The negative
delta is worth a sentence — hedging a put means shorting stock.

(b) Same tree, but the stock goes to 130 or 70 instead. Price the call.
Answer: q is not needed; Δ = 30/60 = 0.5, B = −35/1.02 = −34.31, price 15.69.
Worth noting: more volatility, more valuable option, and delta happened to stay
at 0.5.

(c) Verify put-call parity: 5.88 − 3.92 = 1.96 = 100 − 100/1.02.

Check any of these with:

```
python scripts/binomial.py --S 100 --K 100 --r 0.02 --u 1.1 --d 0.9 --n 1 \
    --kind "European put"
```

The `delta` and `bond` columns are the replicating portfolio, so the script
output maps directly onto what the student just did by hand.

## Where students get stuck

The sign of B. A student who reports 5.88 as `0.5·100 + 44.12 = 94.12` has the
sign backwards. Ask what the bond position has to do to make the portfolio worth
zero in the down state — you need a debt of 45 to cancel 45 of stock.

Believing delta is a probability. It is 0.5 in the running example, which is an
unlucky coincidence. Point at example (b), where delta is still 0.5 with a very
different tree, or just change the strike.

Wanting to discount at a risk-adjusted rate. The instinct is right in general and
unnecessary here: we never took an expectation, so there is nothing to
risk-adjust. Every cash flow in the argument was certain.

Next: `references/02-risk-neutral.md`.
