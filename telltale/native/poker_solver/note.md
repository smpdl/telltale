In this document, I want to go through the poker solver and attempt to explain how the whole thing works. I want to do this so that a) I know that I understand how it all works and b) someone who is looking over this codebase can get a quick introduction to how it works. 

The main idea in making this solver is that I don't want to create the most game theory optimal (GTO) poker solver. This is a small game where you are playing with small LLMs. I want the personality of the agents that are playing the game, the way the game is being played, and things like that to also dictate the strategy of any individial agent. So, there will definitely be cases where the solver will not theoretically/qunatitatively reflect the most sound and reasonable play. But, that is okay. This solver will just serve as a way for the agents to get actual objective information about the game, so that they can reason about what their next move should be on their own. 

## Evaluating a hand of poker

The first thing that we will need to understand is how to evaluate a hand of poker. Out of the 2 hole cards that each player has, and the 5 community cards that is common to all players, we will need to find the best-5 card hand. We will evaluate this by ranking each possible combination and comparing it to the best possible hand that you can make. To do that, we will use a `HandRank` class that will have category, tiebreakers, and label as its attributes. There are only 9 categories of cards in No-limit Texas Hold'em, so we will rank them according to the strength of the hand as follows: 


| Category | Label           | Tiebreakers (in order)              |
| -------- | --------------- | ----------------------------------- |
| 0        | high card       | all five ranks, high to low         |
| 1        | one pair        | pair rank, then kickers high to low |
| 2        | two pair        | high pair, low pair, kicker         |
| 3        | three of a kind | trips rank, then kickers            |
| 4        | straight        | high card of the straight           |
| 5        | flush           | all five ranks, high to low         |
| 6        | full house      | trips rank, then pair rank          |
| 7        | four of a kind  | quad rank, then kicker              |
| 8        | straight flush  | high card of the straight           |


A good thing about this is that a higher category always beats a lower category. And, for cards in the same category, we can just use the tiebreaker cards. Therefore, once we have a `HandRank`, comparing two hands is just a basic comparison:

1. Compare `category` first. A higher category always wins.
2. If categories are equal, compare `tiebreakers` one element at a time, left to right.
3. If all compared tiebreakers match, the hands tie.

`evaluate_5()` takes a hand and returns the HandRank object for it. To do that, it first collects some basic facts about the five cards: how many of each rank appear, whether all five cards share the same suit (a flush), and whether the distinct ranks form a consecutive run (a straight), with a special case for the wheel straight `A-2-3-4-5` where the ace plays low and the high card is 5. It then walks down the category list from strongest to weakest straight and returns as soon as it finds a match, filling in the appropriate tiebreakers along the way. For hands with pairs or better, kickers are the ranks that are not part of the main combination, sorted from highest to lowest.

In Hold'em we rarely evaluate exactly five cards on their own. `evaluate_7()` takes all seven cards (two hole cards plus five community cards), tries every possible five-card subset, there are 21 of them, runs `evaluate_5()` on each, and keeps the strongest result.

## Some Important Decision Features to Know About

This was just basic hand evaluation. It is important now as we move forward to get to something that will actually help us give some information about how strong one's current position is at a given moment and can help us in our decision making.

### Equity

Equity tries to answer the question that given what we know and what is still unknown, **what share of the pot do we expect to win** if the hand runs out?

Conceptually:

$$
\text{equity} = \frac{\mathbb{E}[\text{amount won by hero}]}{\text{total pot}}
$$

We never compute that expectation in closed form. Instead, `estimate_equity()` in `equity.cpp` runs a **Monte Carlo simulation**, where we complete the hand thousands of times at random, count outcomes, and use sample frequencies as probabilities. The same `EquityResult` shape is also returned by `estimate_equity_vs_range()`, which samples opponent hands from a **weighted range** instead of uniformly from the deck.

Before any trial starts, the code builds a **known card set** = hero + board + dead cards, checks that no card appears twice, and builds a **remaining deck** of everything else in the standard 52-card deck.

It also computes how many unknown cards each trial needs:

$$
\text{boardneeded} = 5 - |\text{board}|, \quad
\text{cardsneeded} = \text{boardneeded} + 2 \cdot \text{numopponents}
$$

If `cardsneeded` exceeds the remaining deck size, estimation throws an error saying that there are not enough cards left to deal.

#### Standard mode: `estimate_equity()`

This is what `PokerPolicyWriter` calls during live play. Opponent hole cards are **uniformly random**: any live two-card combo is equally likely, conditional on not conflicting with known cards.

**One trial:**

1. Shuffle the remaining deck with the seeded RNG.
2. Deal `boardneeded` cards off the top to complete the board to five cards.
3. Evaluate the hero with `evaluate_7(hero + board)`.
4. For each opponent, deal two hole cards from the deck and evaluate with `evaluate_7(opponent + board)`.
5. Classify the trial:
   - **Loss**: at least one opponent's hand beats the hero (comparison stops early on the first loss).
   - **Tie**: no opponent beats the hero, but at least one opponent ties.
   - **Win**: the hero has the sole best hand.

Step 5 is important for multiway pots. The hero only wins a trial when nobody beats them and nobody chops. One player outdrawing us is enough for the whole trial to count as a loss, even if we would have tied someone else.

After $N$ iterations:

$$
P(\text{win}) = \frac{\text{wins}}{N}, \quad
P(\text{tie}) = \frac{\text{ties}}{N}, \quad
P(\text{loss}) = \frac{\text{losses}}{N}
$$

Hero equity combines wins and ties:

$$
\text{heroequity} = P(\text{win}) + 0.5 \cdot P(\text{tie})
$$

The factor of $\frac{1}{2}$ on ties reflects chopping: if we tie for the best hand, we only recover half of the contested pot on average.

#### Range mode: `estimate_equity_vs_range()`

The second entry point models a **single opponent** whose hand is drawn from a weighted combo list rather than uniformly from the deck. Each `RangeCombo` is two cards plus a positive weight, e.g. `AhAd:1,KsQs:0.5` via `parse_range_csv()`.

**One trial:**

1. Filter the range to **live combos**: drop any combo that shares a card with hero, board, or dead cards.
2. Sample one combo with probability proportional to its weight.
3. Remove that combo's two cards from the deck, shuffle what is left, and deal out the remaining board cards.
4. Compare hero vs the sampled opponent hand head-to-head (win / tie / loss).

Range mode is heads-up only: there is no `num_opponents` parameter because the opponent hand is defined by the range sample. If every combo conflicts with known cards, estimation throws (`opponent range has no live combos`).

### Pot Odds

Equity tells us how strong our hand is, but pot odds tell us whether the price of continuing is worth paying. When we face a bet, we need to put in more chips to stay in the hand. Pot odds measure that cost as a fraction of the total pot we are fighting for after we call.

If there is nothing to call, pot odds are zero. Otherwise:

$$
\text{potodds} = \frac{\text{amounttocall}}{\text{potsize} + \text{amounttocall}}
$$

The denominator is the pot after we call, because that is the total prize we are contesting once we pay the outstanding amount. For example, if the pot is 100 and we must call 50, then:

$$
\text{potodds} = \frac{50}{100 + 50} = \frac{1}{3} \approx 0.33
$$

So we are risking one third of the final pot to win the whole thing. In the simplest heads-up, one-street model, a call is roughly break-even when:

$$
\text{heroequity} \approx \text{potodds}
$$

If our equity is below pot odds, calling loses money on average; if it is above, calling wins money on average. Real poker is more complicated because future betting streets exist, but this is still a useful baseline.

### Stack-to-Pot Ratio

Stack-to-pot ratio (SPR) measures how deep our remaining stack is relative to the pot. It tells us how much room we have left to bet on later streets, and how close we are to being committed.

$$
\text{SPR} = \frac{\text{herostack}}{\text{potsize}}
$$

If the pot is empty, we define SPR as the hero's full stack so the value is still meaningful as a large number.

A low SPR means the pot is already large compared to what we have left. For example, $\text{SPR} = 0.8$ means our stack is only 80% of the pot, one more reasonable bet can put us all in. A high SPR means we are still deep relative to the pot and have more room to maneuver.

### Board Texture

Board texture is a label for how coordinated and dangerous the community cards are. Two players can have the same equity number on very different boards: a dry rainbow flop is stable, while a monotone connected flop creates many straight and flush possibilities for opponents we have not seen yet.

`board_texture()` in `policy.py` assigns one label once at least three community cards are out. Before the flop, or with fewer than three board cards, the texture is `"dry"`.

The function looks at three properties of the board:

1. **Suit pattern**: how many distinct suits appear.
2. **Pairing**: whether any rank appears more than once.
3. **Connectivity**: whether the ranks contain a three-card straight window (ranks within a span of 4, including the wheel case $A$-$2$-$3$-$4$-$5$).

The labels are assigned in priority order:


| Label       | Meaning                                         |
| ----------- | ----------------------------------------------- |
| `monotone`  | All board cards share one suit                  |
| `wet`       | Connected board that is also two-tone or paired |
| `connected` | Straight-draw potential, but not wet            |
| `paired`    | At least one paired rank on board               |
| `two_tone`  | Exactly two suits on board                      |
| `dry`       | None of the above                               |


`"wet"` boards are the most volatile: they combine connectivity with flush or full-house texture. `"dry"` boards change less when new cards arrive.

# How does the Solver Recommend?

`recommend_action_json()` in `action_policy.cpp` turns `DecisionFeatures` (equity, pot odds, SPR, board texture, legal actions, and history) into a JSON recommendation. It does **not** run CFR or build opponent ranges. It scores each legal action with some weights, normalizes them into probabilities, and returns the top pick plus metadata for agents and prompts.

`PokerPolicyWriter` in `policy.py` is the usual entry point: estimate equity -> build features -> call `native.recommend_action()` → wrap as `PokerDecision`.

## How the recommendation is built

- The policy uses two different weight tables: passive line (check / bet / all-in) vs facing a bet (fold / call / raise / all-in). 
- Each street has a value line (when to bet for value) and a raise line (when raising is reasonable):

| Street | Value line | Raise line |
| ------ | ---------- | ---------- |
| preflop | 0.63 | 0.74 |
| flop | 0.60 | 0.72 |
| turn | 0.58 | 0.70 |
| river | 0.55 | 0.67 |

- If we must call and $\text{equity} + 0.03 < \text{potodds}$, the fold weight spikes. That encodes "don't pay more than our fair share of the pot without a cushion."
- Wet and monotone boards apply a caution multiplier (down to 0.72) on bets and raises. Scary runouts deserve less eagerness to build pots without a strong hand.
- With three or more players left, bet/raise weights are multiplied by 0.72. More opponents means someone is more likely to have us beat.
- `previous_aggression_count` shrinks call/raise weights via an aggression penalty. Stations and repeat bettors are modeled as less attractive to engage lightly.
- `street_action_count` adds a small pressure bonus to betting weights. Repeated action on a street nudges toward continuing the story with a bet.
- All-in only gets meaningful weight when equity is very high (>= 0.82–0.84 depending on line) and SPR is shallow (<= 1.15-1.25). Deep stacks with medium strength should not default to shoving.
- We, will then divide each action's weight by the sum. If nothing qualified, fall back to a uniform distribution over legal actions.
- We will then pick `suggested_action`, the highest probability wins. `decision_margin` is the gap to the runner-up; `confidence` blends margin with $|\text{equity} - \text{potodds}|$.
- `suggested_amount` defaults to roughly half-pot (clamped to min-raise and stack). `amount_options` exposes small / medium / large / all-in chip counts from pot fractions.

## Extra output buckets

| Field | Buckets | Purpose |
| ----- | ------- | ------- |
| `hand_strength_bucket` | weak (< 0.42), medium, strong (<= 0.62), monster (>= 0.82) | Plain-language hand strength for prompts |
| `spr_bucket` | low (<= 1.5), medium (<= 4.0), deep | How committed we are relative to the pot |
| `abstract_actions` | fold, check, call, bet_33/66/100, raise_2_5x, raise_pot, all_in | Advisory sizing vocabulary when those lines are legal |
| `risk_label` | low / medium / high | Rough risk of the top action given SPR, board, and action type |

