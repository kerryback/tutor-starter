# Module 2 — Risk-neutral probabilities

Goal: the student should be able to derive `q`, use it, and say precisely what it
is and is not. Nothing new is being priced here — this is a rewriting of Module
1's answer that happens to scale to large trees.

Do not start this module until the student has priced something by replication.
Risk-neutral valuation taught first is a magic trick; taught second it is a
simplification.

Teach it in this order. In each part, teach the idea and work the example
yourself first, then give the student the practice example and wait.

## 1. Motivate the shortcut

Teach: in Module 1 we priced the call by building a portfolio of stock and bond
that copies it. That took two equations for Δ and B. For a big tree we would
need a new portfolio at every node. So we look for one set of weights on the up
and down states that prices everything in the tree at once. The rest of the
module finds those weights.

## 2. Find the probability that fits the stock

Teach: start with the asset whose price we already know: the stock. Find the
probability q of the up state that makes the stock's expected value,
discounted at the risk-free rate, equal its price today. Write `R = 1 + r`:

```
S = [ q·S_u + (1 − q)·S_d ] / R
```

On the running example, `100 = [q·110 + (1 − q)·90] / 1.02`. Solve it on the
board: `102 = 90 + 20q`, so `q = 0.6`. In general, dividing by S,

```
q·u + (1 − q)·d = R      →      q = (R − d)/(u − d)
```

So q is the probability under which the stock earns the risk-free rate — the
probability a risk-neutral investor would need to hold to be content owning
this stock. Hence the name.

Practice: a stock is at 50 and goes to 60 or 45. The risk-free rate is 3% per
period. What is q? (q = (1.03 − 0.90)/(1.20 − 0.90) = 0.4333.)

## 3. Use q to price the option

Teach: price the call with the same q. Take its expected payoff under q and
discount at the risk-free rate.

```
C = [ q·C_u + (1 − q)·C_d ] / R
```

On the running example, `C = (0.6·10 + 0.4·0)/1.02 = 5.88`.

Point out that this is exactly the Module 1 answer, 5.88, and that it always
will be. The replicating portfolio is Δ shares and B in the bond. q prices the
stock correctly by construction and prices the bond correctly because the
weights add up to one, so q prices the portfolio correctly, and the portfolio
pays what the option pays. If the student wants proof, substitute Module 1's Δ
and B into `C = Δ·S + B` and collect terms; the result is the formula above.

Practice: on the practice tree from part 2 (50, going to 60 or 45, r = 3%),
price a call with strike 50. (`0.4333 · 10 / 1.03 = 4.21`.)

## 4. What q actually is

Three things worth stating plainly, because students carry the opposite belief
out of this material:

1. q is not a forecast. It is not anyone's estimate of anything.
2. Nobody is assumed to be risk neutral. Real investors are risk averse, the
   stock really does earn a risk premium, and none of that changes q.
3. The true probability never appears in the formula. If it did, two investors
   with different beliefs would get different prices, and one of them could be
   arbitraged.

The reason we can get away with it is Module 1: the hedge worked in both states,
so no probability was needed, and q is just the weight that makes a
no-arbitrage answer look like an expected value. The form is an expectation; the
content is replication.

Useful challenge if the student is skeptical: ask them what the stock's expected
return would have to be for the call to be worth something other than 5.88.
There is no such number.

## 5. Why 0 < q < 1 is the no-arbitrage condition

Worth ninety seconds. `q = (R − d)/(u − d)` lies strictly between 0 and 1 exactly
when `d < R < u`. If `R ≤ d` the stock beats the bond in every state and you
should borrow and buy without limit. If `R ≥ u` the reverse. So the requirement
that q be a probability at all is the same as the requirement that no free money
exists.

The script enforces this. Show it breaking:

```
python scripts/binomial.py --S 100 --K 100 --r 0.15 --u 1.1 --d 0.9 --n 1
```

It refuses and says why: 1 + r = 1.15 is above u = 1.10, so the bond beats
the stock in every state.

Practice: u = 1.10, d = 0.90, and r = 12% per period. Is there an arbitrage,
and what is the trade? (Yes: 1.12 is above 1.10, so the bond beats the stock in
every state. Short the stock and lend the proceeds.)

## 6. Fill in the node

Teach: this is the exercise format to use from here on. Present a tree with
the stock prices given and the option values filled in everywhere except one
node, and ask for two numbers: the missing value, and the price today. Show the
format on the running example first, with every value filled in: the call at
5.88, from 10 and 0.

Practice: the one-period version. Give them this and stop:

```
        t=0                t=1
--------------------------------------
                     125.00 /   25.00
  100.00 /       ?
                      80.00 /    0.00

  S = 100, K = 100, r = 5% per period, u = 1.25, d = 0.80
```

Answer: `q = (1.05 − 0.80)/(1.25 − 0.80) = 0.5556`, price
`0.5556 · 25 / 1.05 = 13.23`. Verify with

```
python scripts/binomial.py --S 100 --K 100 --r 0.05 --u 1.25 --d 0.8 --n 1 \
    --kind "European call"
```

Follow-up worth asking: what is the replicating portfolio here, and does it cost
13.23? (Δ = 25/45 = 0.5556, B = −42.33.) Making the student cross-check the two
methods against each other is how the equivalence stops being a claim.

## 7. A backwards one

Teach: running the formula in reverse tests whether they understand it or
have memorized it. Work this one on the board:

> A stock is at 100. It goes up 10% or down to some price you don't know. The
> risk-free rate is 2%. Somebody tells you the risk-neutral probability of an up
> move is 0.6. What is the down price?

Answer: `0.6(1.1 − d) = 1.02 − d` gives `d = 0.9`, so 90.

Practice: a stock is at 50. It goes up 20% or down to a price you don't know.
The risk-free rate is 3%, and the risk-neutral probability of an up move is
0.5. What is the down price? (`0.5(1.2 − d) = 1.03 − d` gives `d = 0.86`, so
43.)

Teach: hold u and d fixed and raise r. q and the call price both go up. Explain
the second in terms of the replicating portfolio. In a one-period tree delta
does not depend on r, so the share position is the same. The borrowing is the
difference: the hedge repays a fixed amount at date 1, 0.5·90 = 45 in the
running example, and a higher r means that repayment supports less borrowing
today. Less borrowed means more of your own money in the portfolio, so the call
costs more. That is the honest explanation; "higher discount rate" is not.

Practice: the running example with r = 4% instead of 2%. What are q and the
call price? (q = 0.7, call 6.73.) Then: what are Δ and B now? (Δ = 0.5,
unchanged; B = −45/1.04 = −43.27, less borrowing.)

## 8. Check understanding

Offer these, one at a time:

(a) Same tree as the running example, price the put with q. Answer:
`(0.4 · 10)/1.02 = 3.92`, matching the portfolio calculation from Module 1.

(b) Suppose the true probability of an up move is 0.8, so the stock's expected
price is 106. Does the call price change? Answer: no. If they hesitate, ask them
which line of the replication argument used 0.8.

(c) The stock's expected return under q. Answer: `0.6·1.1 + 0.4·0.9 = 1.02`, the
risk-free rate, by construction.

Next: `references/03-multiperiod.md`.
