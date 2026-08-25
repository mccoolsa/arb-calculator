"""One log schema shared by calculated and manually recorded bets.

An arbitrage, an expected-value wager and a bet typed in by hand describe
very different positions, but a log is only useful if every row answers the
same questions. Each kind is therefore mapped onto one set of columns:

    Date, Name, Type, Sport, Selection, Bet Type, Each Way, Event,
    Bookmaker, Odds, Stake, Payout, Projected P/L, Realised P/L, Status,
    Notes

The numeric columns stay as numbers (never "$1,234.56") so the exported CSV
opens cleanly in Excel or Power BI without a parsing pass.
"""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import date

from . import core
from .storage import ARBITRAGE, DEFAULT_STATUS, EV, MANUAL

#: Offered by the sport dropdown. The leading blank means "not recorded",
#: which is different from "Other" - bets saved before the field existed
#: have no sport at all.
SPORTS = ("", "Soccer", "GAA", "Basketball", "CS", "Valorant", "Horse Racing",
          "Greyhounds", "Darts", "Golf", "MMA/Boxing", "Other")

#: How many selections the bet carries. New bets default to Single.
BET_TYPES = ("", "Single", "Double", "Treble", "Accum")
DEFAULT_BET_TYPE = "Single"

#: Each-way place terms, offered when the each-way box is ticked. A fifth
#: of the odds is much the commonest, so that is what a new bet starts on.
PLACE_TERMS = ("1/2", "1/3", "1/4", "1/5")
DEFAULT_PLACE_TERMS = "1/5"

CSV_COLUMNS = ("Date", "Name", "Type", "Sport", "Selection", "Bet Type",
               "Each Way", "Event", "Bookmaker", "Odds", "Stake", "Payout",
               "Projected P/L", "Realised P/L", "Status", "Notes")

#: "P/L" is a display-only column: the realised figure once a bet is settled,
#: the projection while it is still running. The export keeps the two apart.
ALL_KEYS = CSV_COLUMNS + ("P/L",)

#: Columns worth showing on screen. The rest are export-only: "Type"
#: duplicates the filter row above the table, "Name" duplicates
#: "Selection", and the each-way terms ride along on "Bet Type".
TABLE_COLUMNS = ("Date", "Sport", "Selection", "Bet Type",
                 "Odds", "Stake", "Payout", "P/L", "Status")

NUMERIC_COLUMNS = ("Stake", "Payout", "Projected P/L", "Realised P/L", "P/L")

#: Date windows offered by the log's period dropdown.
PERIODS = (
    ("all", "All time"),
    ("today", "Today"),
    ("7", "Last 7 days"),
    ("30", "Last 30 days"),
    ("month", "This month"),
    ("year", "This year"),
)

TYPE_LABELS = {
    ARBITRAGE: "Arbitrage",
    EV: "Expected Value",
    MANUAL: "Manual",
}


def _number(value):
    """Coerce a stored value to a float, or None if it is not usable."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _bet_date(bet: dict) -> str:
    inputs = bet.get("inputs") or {}
    if inputs.get("date"):
        return str(inputs["date"])
    return str(bet.get("created", ""))[:10]


def _odds_text(bet: dict) -> str:
    kind = bet.get("kind")
    inputs = bet.get("inputs") or {}
    results = bet.get("results") or {}
    fmt = inputs.get("odds_format", core.DECIMAL)
    try:
        if kind == ARBITRAGE:
            return "{} / {}".format(core.format_odds(results["odds_a"], fmt),
                                    core.format_odds(results["odds_b"], fmt))
        if kind == EV:
            return core.format_odds(results["odds"], fmt)
    except (KeyError, TypeError, core.OddsError):
        return ""
    return str(inputs.get("odds", "") or "")


def realised_pl(stake, payout, status):
    """What a settled bet actually returned. ``None`` while still pending.

    A losing bet costs its stake, a void bet is a wash, and a winner returns
    its payout less the stake. A winner with no payout recorded cannot be
    worked out, so it stays blank rather than being guessed at.
    """
    if status == "Void":
        return 0.0
    if status == "Lost":
        return None if stake is None else -stake
    if status == "Won":
        if stake is None or payout is None:
            return None
        return payout - stake
    return None


def log_row(bet: dict) -> dict:
    """Flatten any saved bet into the shared log schema."""
    kind = bet.get("kind", MANUAL)
    inputs = bet.get("inputs") or {}
    results = bet.get("results") or {}

    row = dict.fromkeys(ALL_KEYS, "")
    row["Date"] = _bet_date(bet)
    row["Name"] = bet.get("name", "")
    row["Type"] = TYPE_LABELS.get(kind, str(kind).title())
    row["Odds"] = _odds_text(bet)
    row["Status"] = bet.get("status", DEFAULT_STATUS)
    row["Notes"] = inputs.get("notes", "") or bet.get("note", "") or ""

    # Selection identifies the row on screen, so fall back to the bet's
    # name rather than leaving it blank or showing a constant that the
    # Type column already says.
    name = bet.get("name") or ""

    if kind == ARBITRAGE:
        row["Selection"] = name or "Both sides (hedge)"
        row["Stake"] = _number(results.get("total_stake"))
        # The guaranteed return is the smaller of the two payouts.
        payouts = [_number(results.get("payout_a")), _number(results.get("payout_b"))]
        payouts = [p for p in payouts if p is not None]
        row["Payout"] = min(payouts) if payouts else None
        row["Projected P/L"] = _number(results.get("worst_profit"))

    elif kind == EV:
        row["Selection"] = name or "Single wager"
        stake = _number(results.get("stake"))
        profit = _number(results.get("profit_if_win"))
        row["Stake"] = stake
        row["Payout"] = (stake + profit) if None not in (stake, profit) else None
        row["Projected P/L"] = _number(results.get("expected_value"))

    else:
        row["Selection"] = inputs.get("selection", "") or name
        row["Sport"] = inputs.get("sport", "") or ""
        bet_type = inputs.get("bet_type", "") or ""
        if inputs.get("each_way"):
            row["Each Way"] = inputs.get("place_terms", "") or ""
            # The table has no room for its own column, so say it here.
            bet_type = (bet_type + " e/w").strip()
        row["Bet Type"] = bet_type
        row["Event"] = inputs.get("event", "") or ""
        row["Bookmaker"] = inputs.get("bookmaker", "") or ""
        row["Stake"] = _number(inputs.get("stake"))
        payout = _number(inputs.get("payout"))
        if payout is None:
            # No payout typed in, so fall back to what the recorded odds and
            # stake imply. A winner still reports what it made, and typing a
            # payout in overrides this for boosts, each-way or partial
            # cash-outs.
            payout = suggested_payout(
                inputs.get("odds"), inputs.get("stake"),
                inputs.get("odds_format", core.DECIMAL),
                each_way=bool(inputs.get("each_way")),
                place_terms=inputs.get("place_terms"))
        row["Payout"] = payout
        # Recomputed rather than read back from storage, so editing the odds
        # updates the projection instead of leaving a stale figure.
        row["Projected P/L"] = (payout - row["Stake"]
                                if None not in (payout, row["Stake"]) else None)

    row["Realised P/L"] = realised_pl(row["Stake"], row["Payout"], row["Status"])
    # Once settled the realised figure is the honest one to show; before that
    # the projection is all there is.
    row["P/L"] = (row["Projected P/L"] if row["Status"] == DEFAULT_STATUS
                  else row["Realised P/L"])
    return row


def parse_date(text):
    """A YYYY-MM-DD string as a date, or None if it is not one."""
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def in_period(row_date, period: str, today=None) -> bool:
    """Whether a bet's date falls inside one of :data:`PERIODS`."""
    if period == "all":
        return True
    when = parse_date(row_date)
    if when is None:
        return False
    today = today or date.today()
    if period == "today":
        return when == today
    if period in ("7", "30"):
        return 0 <= (today - when).days < int(period)
    if period == "month":
        return (when.year, when.month) == (today.year, today.month)
    if period == "year":
        return when.year == today.year
    return True


def manual_results(stake, payout) -> dict:
    """The derived half of a hand-entered bet."""
    stake_value = _number(stake)
    payout_value = _number(payout)
    profit = None
    if stake_value is not None and payout_value is not None:
        profit = payout_value - stake_value
    return {"stake": stake_value, "payout": payout_value,
            "projected_profit": profit}


def suggested_payout(odds_text, stake, odds_format=core.DECIMAL,
                     each_way=False, place_terms=None):
    """What the bet returns if it wins. None if it cannot be worked out.

    For an each-way bet that is both halves paying out, since a winner
    places as well.
    """
    stake_value = _number(stake)
    if stake_value is None:
        return None
    try:
        decimal_odds = core.parse_odds_loose(odds_text, odds_format)
        if each_way:
            fraction = core.parse_place_terms(
                place_terms or DEFAULT_PLACE_TERMS)
            return core.compute_each_way(
                stake_value, decimal_odds, fraction).win_return
    except core.OddsError:
        return None
    return stake_value * decimal_odds


def each_way_breakdown(odds_text, stake, odds_format=core.DECIMAL,
                       place_terms=None):
    """The split and both returns, for the note under the each-way box."""
    stake_value = _number(stake)
    if stake_value is None:
        return None
    try:
        decimal_odds = core.parse_odds_loose(odds_text, odds_format)
        fraction = core.parse_place_terms(place_terms or DEFAULT_PLACE_TERMS)
        return core.compute_each_way(stake_value, decimal_odds, fraction)
    except core.OddsError:
        return None


def totals(bets) -> dict:
    """Headline figures for the log.

    Open bets contribute their projection, settled ones their actual return,
    and the two are kept apart so a run of losses cannot hide behind what the
    still-running bets might do.
    """
    rows = [log_row(b) for b in bets]
    open_rows = [r for r in rows if r["Status"] == DEFAULT_STATUS]
    settled_rows = [r for r in rows if r["Status"] != DEFAULT_STATUS]

    settled = sum(r["Realised P/L"] or 0.0 for r in settled_rows)
    settled_stake = sum(r["Stake"] or 0.0 for r in settled_rows)

    return {
        "count": len(rows),
        "staked": sum(r["Stake"] or 0.0 for r in rows),
        "open_count": len(open_rows),
        "projected": sum(r["Projected P/L"] or 0.0 for r in open_rows),
        "settled_count": len(settled_rows),
        "settled": settled,
        "settled_stake": settled_stake,
        "roi_pct": (settled / settled_stake * 100.0) if settled_stake else 0.0,
    }


def csv_cell(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return "{:.2f}".format(value)
    return str(value)


def default_filename(today=None) -> str:
    return "bet-log-{}.csv".format(today or date.today().isoformat())


def export_csv(bets, path: str) -> int:
    """Write the bets to ``path`` as CSV. Returns the number of rows written.

    Encoded utf-8-sig so Excel picks up the encoding without being told.
    Written to a temp file first, so a failure never truncates an existing
    export.
    """
    rows = [log_row(bet) for bet in bets]
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_COLUMNS)
            for row in rows:
                writer.writerow([csv_cell(row[column]) for column in CSV_COLUMNS])
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return len(rows)
