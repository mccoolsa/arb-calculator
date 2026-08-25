"""Core betting mathematics.

The methodology here mirrors the OddsJam arbitrage (hedge) calculator and
expected value calculator exactly.

Arbitrage / hedge
-----------------
Two-way market, decimal odds ``o_a`` and ``o_b``, with independent stakes on
each side. Each outcome is evaluated on its own::

    payout_x = stake_x * o_x
    profit_x = payout_x - (stake_a + stake_b)
    return_x = profit_x / payout_x

The payouts do not have to match. When they are deliberately equalised - the
hedge the reference tool sizes for you - both outcomes collapse to a single
figure::

    stake_b = stake_a * o_a / o_b
    payout  = stake_a * o_a          (identical on both sides)
    profit  = payout - (stake_a + stake_b)
    profit% = profit / payout

Worked example from the reference tool: odds 1.80 / 3.70, stake 100.
    stake_b = 100 * 1.80 / 3.70 = 48.65
    payout  = 180.00 on both sides
    total staked = 148.65, profit = 31.35, profit% = 31.35 / 180 = 17.42%

An arbitrage exists when the summed implied probabilities are under 100%::

    1/o_a + 1/o_b < 1

Expected value
--------------
    EV = (fair win probability) x (profit if win)
       - (fair loss probability) x (stake)

Worked example from the reference tool: $100 on +110 (decimal 2.10) with a
fair win probability of 50% gives 0.50 x 110 - 0.50 x 100 = $5.00.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from fractions import Fraction

DECIMAL = "decimal"
AMERICAN = "american"
FRACTIONAL = "fractional"

#: The traditional bookmaker price ladder, shortest to longest. Fractional
#: odds move between these rungs rather than by a fixed increment - 4/5 steps
#: up to 5/6, not to some arithmetic neighbour that no book would price.
FRACTIONAL_LADDER = (
    "1/100 1/66 1/50 1/40 1/33 1/25 1/20 1/16 1/14 1/12 1/10 1/9 1/8 1/7 1/6 "
    "1/5 2/9 1/4 2/7 3/10 1/3 4/11 2/5 4/9 1/2 8/15 4/7 8/13 2/3 8/11 4/5 "
    "5/6 10/11 1/1 11/10 6/5 5/4 11/8 3/2 8/5 13/8 7/4 15/8 2/1 9/4 5/2 11/4 "
    "3/1 10/3 7/2 4/1 9/2 5/1 11/2 6/1 13/2 7/1 15/2 8/1 17/2 9/1 10/1 11/1 "
    "12/1 14/1 16/1 18/1 20/1 22/1 25/1 28/1 33/1 40/1 50/1 66/1 80/1 100/1"
).split()


class OddsError(ValueError):
    """Raised when odds or stakes fall outside a usable range."""


# --------------------------------------------------------------------------
# Odds conversion
# --------------------------------------------------------------------------

def american_to_decimal(american: float) -> float:
    """Convert American (moneyline) odds to decimal odds."""
    if american >= 100:
        return 1.0 + american / 100.0
    if american <= -100:
        return 1.0 + 100.0 / abs(american)
    raise OddsError("American odds must be +100 or longer, or -100 or shorter.")


def decimal_to_american(decimal_odds: float) -> float:
    """Convert decimal odds to American (moneyline) odds."""
    if decimal_odds <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    if decimal_odds >= 2.0:
        return (decimal_odds - 1.0) * 100.0
    return -100.0 / (decimal_odds - 1.0)


def fractional_to_decimal(numerator: float, denominator: float) -> float:
    """Convert fractional (UK / Irish) odds to decimal odds: 5/4 -> 2.25."""
    if numerator <= 0 or denominator <= 0:
        raise OddsError("Fractional odds must be positive, like 5/4.")
    return numerator / denominator + 1.0


def decimal_to_fractional(decimal_odds: float, max_denominator: int = 100) -> str:
    """Convert decimal odds to the nearest tidy fraction: 1.80 -> '4/5'."""
    if decimal_odds <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    frac = Fraction(decimal_odds - 1.0).limit_denominator(max_denominator)
    return "{}/{}".format(frac.numerator, frac.denominator)


def parse_fractional(raw) -> float:
    """Parse '5/4', '5-4', '5:4', 'evens' or a bare '5' into decimal odds."""
    text = str(raw or "").strip().lower().replace(" ", "").replace(",", "")
    if not text:
        raise OddsError("Enter odds.")
    if text in ("evens", "evs", "even"):
        return 2.0

    separator = next((s for s in ("/", ":", "-") if s in text), None)
    try:
        if separator is None:
            numerator, denominator = float(text), 1.0
        else:
            left, _, right = text.partition(separator)
            numerator, denominator = float(left), float(right)
    except ValueError:
        raise OddsError("Fractional odds look like 5/4.") from None
    return fractional_to_decimal(numerator, denominator)


def step_fractional(raw, direction: int):
    """Move one rung along the bookmaker ladder. ``None`` if unparseable."""
    try:
        current = parse_fractional(raw)
    except OddsError:
        return None
    rungs = [(parse_fractional(f), f) for f in FRACTIONAL_LADDER]
    if direction > 0:
        return next((f for value, f in rungs if value > current + 1e-9),
                    rungs[-1][1])
    return next((f for value, f in reversed(rungs) if value < current - 1e-9),
                rungs[0][1])


def parse_odds(raw, odds_format: str = DECIMAL) -> float:
    """Parse a user-entered odds string into decimal odds."""
    if odds_format == FRACTIONAL:
        return parse_fractional(raw)
    if raw is None:
        raise OddsError("Enter odds.")
    text = str(raw).strip().replace(",", "")
    if not text:
        raise OddsError("Enter odds.")
    try:
        value = float(text)
    except ValueError:
        raise OddsError("Odds must be a number.") from None

    if odds_format == AMERICAN:
        return american_to_decimal(value)
    if value <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    return value


def infer_odds_format(raw):
    """Guess a format from how the odds are written. None if unclear."""
    text = str(raw or "").strip().lower().replace(" ", "")
    if not text:
        return None
    if text in ("evens", "evs", "even"):
        return FRACTIONAL
    # "8/11", "5:4", "5-4" - but not the leading minus of "-137"
    if "/" in text or ":" in text or "-" in text[1:]:
        return FRACTIONAL
    try:
        value = float(text)
    except ValueError:
        return None
    if text.startswith(("+", "-")) or abs(value) >= 100:
        return AMERICAN
    if value > 1.0:
        return DECIMAL
    return None


def parse_odds_loose(raw, preferred: str = DECIMAL) -> float:
    """Parse odds, falling back to whatever the text actually looks like.

    A bet can be saved with a format label that does not match what was
    typed - fractional odds entered while the format toggle said decimal,
    say. The text is the better evidence, so honour it rather than refusing
    to read the price.
    """
    try:
        return parse_odds(raw, preferred)
    except OddsError:
        inferred = infer_odds_format(raw)
        if inferred is None or inferred == preferred:
            raise
        return parse_odds(raw, inferred)


def format_odds(decimal_odds: float, odds_format: str = DECIMAL) -> str:
    """Render decimal odds the way the given input format writes them."""
    if odds_format == AMERICAN:
        american = decimal_to_american(decimal_odds)
        return ("+" if american > 0 else "") + "{:.0f}".format(american)
    if odds_format == FRACTIONAL:
        return decimal_to_fractional(decimal_odds)
    return "{:.2f}".format(decimal_odds)


def parse_amount(raw, label: str = "Amount", allow_zero: bool = True) -> float:
    """Parse a user-entered money / numeric amount."""
    text = str(raw or "").strip().replace(",", "").replace("$", "")
    if not text:
        raise OddsError("Enter a " + label.lower() + ".")
    try:
        value = float(text)
    except ValueError:
        raise OddsError(label + " must be a number.") from None
    if value < 0 or (value == 0 and not allow_zero):
        raise OddsError(label + " must be positive.")
    return value


def implied_probability(decimal_odds: float) -> float:
    """Implied win probability (0-1) of decimal odds, including the vig."""
    if decimal_odds <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    return 1.0 / decimal_odds


# --------------------------------------------------------------------------
# Arbitrage / hedge
# --------------------------------------------------------------------------

#: Each-way place terms: the fraction of the odds the place part runs at.
PLACE_FRACTIONS = {"1/2": 0.5, "1/3": 1.0 / 3.0, "1/4": 0.25, "1/5": 0.2}


def parse_place_terms(raw) -> float:
    """'1/5' -> 0.2. Any 'n/d' is accepted, not just the usual four."""
    text = str(raw or "").strip().replace(" ", "")
    if text in PLACE_FRACTIONS:
        return PLACE_FRACTIONS[text]
    numerator, separator, denominator = text.partition("/")
    if not separator:
        raise OddsError("Place terms look like 1/5.")
    try:
        top, bottom = float(numerator), float(denominator)
    except ValueError:
        raise OddsError("Place terms look like 1/5.") from None
    if top <= 0 or bottom <= 0:
        raise OddsError("Place terms must be positive, like 1/5.")
    return top / bottom


@dataclass(frozen=True)
class EachWayResult:
    stake: float                # the whole outlay
    win_stake: float            # half of it, on the win
    place_stake: float          # the other half, on the place
    odds: float
    place_odds: float
    place_fraction: float
    win_return: float           # back if it wins - both halves pay
    place_return: float         # back if it only places
    win_profit: float
    place_profit: float

    def as_dict(self) -> dict:
        return asdict(self)


def compute_each_way(stake: float, decimal_odds: float,
                     place_fraction: float) -> EachWayResult:
    """An each-way bet with the stake split half win, half place.

    The place half runs at a fraction of the odds, so 8/1 at 1/5 terms
    places at 8/5. Winning pays both halves; placing pays only the second;
    finishing out of the places pays nothing.

    Note this treats ``stake`` as the *total* outlay. A bookmaker writing
    "10 each way" means 10 on each half and 20 out of your pocket, so 10
    each way in their sense is a stake of 20 here.
    """
    if decimal_odds <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    if stake < 0:
        raise OddsError("Stake must be positive.")
    if not 0 < place_fraction <= 1:
        raise OddsError("Place terms must be a fraction such as 1/5.")

    half = stake / 2.0
    place_odds = 1.0 + (decimal_odds - 1.0) * place_fraction
    win_return = half * decimal_odds + half * place_odds
    place_return = half * place_odds

    return EachWayResult(
        stake=stake,
        win_stake=half,
        place_stake=half,
        odds=decimal_odds,
        place_odds=place_odds,
        place_fraction=place_fraction,
        win_return=win_return,
        place_return=place_return,
        win_profit=win_return - stake,
        place_profit=place_return - stake,
    )


def hedge_stake(stake: float, odds_from: float, odds_to: float) -> float:
    """Stake on the other side that makes both payouts equal.

        stake_to = stake_from * odds_from / odds_to
    """
    if odds_from <= 1.0 or odds_to <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    if stake < 0:
        raise OddsError("Stake must be positive.")
    return stake * odds_from / odds_to


@dataclass(frozen=True)
class TwoWayResult:
    odds_a: float
    odds_b: float
    stake_a: float
    stake_b: float
    payout_a: float
    payout_b: float
    total_stake: float
    profit_a: float             # profit if side A wins
    profit_b: float             # profit if side B wins
    return_a_pct: float         # profit_a / payout_a - the reference tool's denominator
    return_b_pct: float
    roi_a_pct: float            # profit_a / total staked (classic ROI)
    roi_b_pct: float
    worst_profit: float
    best_profit: float
    is_hedged: bool             # side B is sized (to the cent) for an equal payout
    hedge_stake_b: float        # stake_b that *would* equalise the payouts
    implied_total_pct: float    # 1/o_a + 1/o_b, as a percentage
    is_arbitrage: bool          # these stakes profit on both outcomes
    market_has_arbitrage: bool  # the odds allow an arb at equal-payout sizing

    def as_dict(self) -> dict:
        return asdict(self)


def compute_two_way(odds_a: float, odds_b: float,
                    stake_a: float, stake_b: float) -> TwoWayResult:
    """Result of backing both sides of a two-way market with any two stakes.

    The stakes are independent - the payouts are only equal if they happen to
    be sized that way. Each outcome is reported separately::

        payout_x = stake_x * odds_x
        profit_x = payout_x - (stake_a + stake_b)

    A guaranteed profit (an arbitrage) means every outcome clears zero, i.e.
    ``min(profit_a, profit_b) > 0``. Sizing both sides for an equal payout is
    what maximises that worst case; see :func:`hedge_stake`.
    """
    if odds_a <= 1.0 or odds_b <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    if stake_a < 0 or stake_b < 0:
        raise OddsError("Stake must be positive.")

    payout_a = stake_a * odds_a
    payout_b = stake_b * odds_b
    total_stake = stake_a + stake_b
    profit_a = payout_a - total_stake
    profit_b = payout_b - total_stake

    implied_total = (1.0 / odds_a + 1.0 / odds_b) * 100.0

    return TwoWayResult(
        odds_a=odds_a,
        odds_b=odds_b,
        stake_a=stake_a,
        stake_b=stake_b,
        payout_a=payout_a,
        payout_b=payout_b,
        total_stake=total_stake,
        profit_a=profit_a,
        profit_b=profit_b,
        return_a_pct=(profit_a / payout_a * 100.0) if payout_a else 0.0,
        return_b_pct=(profit_b / payout_b * 100.0) if payout_b else 0.0,
        roi_a_pct=(profit_a / total_stake * 100.0) if total_stake else 0.0,
        roi_b_pct=(profit_b / total_stake * 100.0) if total_stake else 0.0,
        worst_profit=min(profit_a, profit_b),
        best_profit=max(profit_a, profit_b),
        # Judge the sizing, not the payouts: a stake rounded to the cent
        # shifts its payout by up to a cent x the odds.
        is_hedged=abs(stake_b - hedge_stake(stake_a, odds_a, odds_b)) < 0.01,
        hedge_stake_b=hedge_stake(stake_a, odds_a, odds_b),
        implied_total_pct=implied_total,
        is_arbitrage=min(profit_a, profit_b) > 0,
        market_has_arbitrage=implied_total < 100.0,
    )


def compute_arbitrage(odds_a: float, odds_b: float,
                      stake_a: float) -> TwoWayResult:
    """The reference tool's calculation: side B sized for an equal payout."""
    return compute_two_way(odds_a, odds_b, stake_a,
                           hedge_stake(stake_a, odds_a, odds_b))


# --------------------------------------------------------------------------
# Expected value
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EVResult:
    stake: float
    odds: float
    win_probability: float          # 0-1
    profit_if_win: float
    loss_if_lose: float
    expected_value: float
    ev_pct: float                   # EV as a percentage of stake
    break_even_probability: float   # 1 / decimal odds
    fair_odds: float                # decimal odds implied by the entered probability
    edge_pct: float                 # win probability - break-even probability

    def as_dict(self) -> dict:
        return asdict(self)


def compute_ev(stake: float, odds: float, win_probability: float) -> EVResult:
    """Expected value of a wager.

    ``odds`` are decimal, ``win_probability`` is a fraction between 0 and 1
    (the fair / no-vig probability, from a model or a sharp book).

        EV = p x (stake x (odds - 1)) - (1 - p) x stake
    """
    if odds <= 1.0:
        raise OddsError("Decimal odds must be greater than 1.00.")
    if stake < 0:
        raise OddsError("Wager must be positive.")
    if not 0.0 <= win_probability <= 1.0:
        raise OddsError("Win probability must be between 0% and 100%.")

    profit_if_win = stake * (odds - 1.0)
    loss_if_lose = stake
    ev = win_probability * profit_if_win - (1.0 - win_probability) * loss_if_lose
    ev_pct = (ev / stake * 100.0) if stake else 0.0
    break_even = 1.0 / odds
    fair_odds = (1.0 / win_probability) if win_probability > 0 else float("inf")

    return EVResult(
        stake=stake,
        odds=odds,
        win_probability=win_probability,
        profit_if_win=profit_if_win,
        loss_if_lose=loss_if_lose,
        expected_value=ev,
        ev_pct=ev_pct,
        break_even_probability=break_even,
        fair_odds=fair_odds,
        edge_pct=(win_probability - break_even) * 100.0,
    )


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def money(value: float, symbol: str = "$") -> str:
    sign = "-" if value < 0 else ""
    return "{}{}{:,.2f}".format(sign, symbol, abs(value))


def pct(value: float, places: int = 2) -> str:
    return "{:.{p}f}%".format(value, p=places)


def odds_label(decimal_odds: float, odds_format: str = DECIMAL) -> str:
    """Odds in the working format, with the decimal equivalent alongside.

    Decimal mode cross-references American instead, since the decimal figure
    would otherwise be printed twice: '2.10 (+110)', '+110 (2.10)', '11/10
    (2.10)'.
    """
    try:
        if odds_format == DECIMAL:
            return "{:.2f} ({})".format(decimal_odds,
                                        format_odds(decimal_odds, AMERICAN))
        return "{} ({:.2f})".format(format_odds(decimal_odds, odds_format),
                                    decimal_odds)
    except OddsError:
        return "{:.2f}".format(decimal_odds)
