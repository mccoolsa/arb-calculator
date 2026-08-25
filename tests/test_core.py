"""Checks the maths against the worked examples in the reference tool.

Runs standalone (``python tests/test_core.py``) or under pytest.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from betting_calc import core  # noqa: E402
from betting_calc.storage import ARBITRAGE, BetStore  # noqa: E402


def approx(a, b, tol=0.005):
    return abs(a - b) < tol


# -- odds conversion -------------------------------------------------------

def test_american_to_decimal():
    assert approx(core.american_to_decimal(110), 2.10)
    assert approx(core.american_to_decimal(-105), 1.952380)
    assert approx(core.american_to_decimal(100), 2.00)


def test_decimal_to_american():
    assert approx(core.decimal_to_american(2.10), 110)
    assert approx(core.decimal_to_american(1.80), -125)
    assert approx(core.decimal_to_american(3.70), 270)


def test_round_trip():
    for american in (-400, -150, -105, 100, 110, 250, 900):
        back = core.decimal_to_american(core.american_to_decimal(american))
        assert approx(back, american, tol=0.01)


# -- fractional odds -------------------------------------------------------

def test_fractional_to_decimal():
    assert approx(core.fractional_to_decimal(5, 4), 2.25)
    assert approx(core.fractional_to_decimal(4, 5), 1.80)
    assert approx(core.fractional_to_decimal(1, 1), 2.00)


def test_decimal_to_fractional_uses_familiar_prices():
    assert core.decimal_to_fractional(1.80) == "4/5"
    assert core.decimal_to_fractional(3.70) == "27/10"
    assert core.decimal_to_fractional(2.20) == "6/5"
    assert core.decimal_to_fractional(2.10) == "11/10"     # +110
    assert core.decimal_to_fractional(2.00) == "1/1"       # evens
    assert core.decimal_to_fractional(5.00) == "4/1"
    assert core.decimal_to_fractional(core.american_to_decimal(-105)) == "20/21"


def test_parse_fractional_accepts_the_usual_spellings():
    for text in ("5/4", "5:4", "5-4", " 5 / 4 "):
        assert approx(core.parse_fractional(text), 2.25)
    assert approx(core.parse_fractional("evens"), 2.00)
    assert approx(core.parse_fractional("EVS"), 2.00)
    assert approx(core.parse_fractional("3"), 4.00)        # bare 3 means 3/1


def test_fractional_rejects_nonsense():
    for text in ("", "abc", "5/0", "0/1", "-5/4", "4/-5"):
        try:
            core.parse_fractional(text)
        except core.OddsError:
            pass
        else:
            raise AssertionError("expected OddsError for {!r}".format(text))


def test_fractional_round_trips_through_decimal():
    for text in ("1/4", "4/5", "1/1", "11/10", "5/4", "2/1", "9/2", "20/21"):
        decimal_odds = core.parse_fractional(text)
        assert core.decimal_to_fractional(decimal_odds) == text


def test_fractional_steps_along_the_bookmaker_ladder():
    assert core.step_fractional("4/5", 1) == "5/6"
    assert core.step_fractional("5/6", -1) == "4/5"
    assert core.step_fractional("1/1", 1) == "11/10"
    assert core.step_fractional("2/1", -1) == "15/8"
    # an off-ladder price moves to the neighbouring rung, not to itself
    assert core.step_fractional("27/10", 1) == "11/4"
    assert core.step_fractional("27/10", -1) == "5/2"
    # the ends of the ladder hold
    assert core.step_fractional("100/1", 1) == "100/1"
    assert core.step_fractional("1/100", -1) == "1/100"
    assert core.step_fractional("nonsense", 1) is None


def test_ladder_is_ordered_and_valid():
    values = [core.parse_fractional(f) for f in core.FRACTIONAL_LADDER]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_infer_odds_format_reads_the_shape():
    assert core.infer_odds_format("8/11") == core.FRACTIONAL
    assert core.infer_odds_format("5-4") == core.FRACTIONAL
    assert core.infer_odds_format("evens") == core.FRACTIONAL
    assert core.infer_odds_format("-137") == core.AMERICAN
    assert core.infer_odds_format("+250") == core.AMERICAN
    assert core.infer_odds_format("150") == core.AMERICAN
    assert core.infer_odds_format("2.20") == core.DECIMAL
    assert core.infer_odds_format("") is None
    assert core.infer_odds_format("abc") is None


def test_parse_odds_loose_survives_a_mislabelled_format():
    """Fractional odds typed while the toggle said decimal must still read."""
    assert approx(core.parse_odds_loose("8/11", core.DECIMAL), 1.72727)
    assert approx(core.parse_odds_loose("-137", core.DECIMAL), 1.72993, tol=0.01)
    # a value the stated format can read is taken at face value
    assert approx(core.parse_odds_loose("2.20", core.DECIMAL), 2.20)
    assert approx(core.parse_odds_loose("5/4", core.FRACTIONAL), 2.25)
    # genuinely unreadable stays an error
    try:
        core.parse_odds_loose("banana", core.DECIMAL)
    except core.OddsError:
        pass
    else:
        raise AssertionError("expected OddsError")


def test_format_odds_covers_every_format():
    assert core.format_odds(2.10, core.DECIMAL) == "2.10"
    assert core.format_odds(2.10, core.AMERICAN) == "+110"
    assert core.format_odds(2.10, core.FRACTIONAL) == "11/10"
    assert core.format_odds(1.80, core.AMERICAN) == "-125"


def test_parse_odds_dispatches_on_format():
    assert approx(core.parse_odds("5/4", core.FRACTIONAL), 2.25)
    assert approx(core.parse_odds("evens", core.FRACTIONAL), 2.00)
    # every format describes the same price
    for fmt, text in ((core.DECIMAL, "2.10"), (core.AMERICAN, "+110"),
                      (core.FRACTIONAL, "11/10")):
        assert approx(core.parse_odds(text, fmt), 2.10)


# -- each way -------------------------------------------------------------

def test_place_terms_parse():
    assert approx(core.parse_place_terms("1/2"), 0.5)
    assert approx(core.parse_place_terms("1/3"), 0.33333)
    assert approx(core.parse_place_terms("1/4"), 0.25)
    assert approx(core.parse_place_terms("1/5"), 0.2)
    assert approx(core.parse_place_terms("1 / 6"), 0.16667)   # not just the four
    for bad in ("", "abc", "1/0", "0/5", "5"):
        try:
            core.parse_place_terms(bad)
        except core.OddsError:
            pass
        else:
            raise AssertionError("expected OddsError for {!r}".format(bad))


def test_each_way_splits_the_stake_in_half():
    """10 at 8/1 with 1/5 terms: 5 on the win, 5 on the place at 8/5."""
    r = core.compute_each_way(10.0, core.parse_fractional("8/1"), 0.2)
    assert approx(r.win_stake, 5.00) and approx(r.place_stake, 5.00)
    assert approx(r.place_odds, 2.60)                # 1 + 8 x 1/5 = 8/5
    assert approx(r.win_return, 58.00)               # 5x9 + 5x2.6
    assert approx(r.place_return, 13.00)             # 5x2.6
    assert approx(r.win_profit, 48.00)
    assert approx(r.place_profit, 3.00)              # still ahead on a place


def test_each_way_matches_the_bookmakers_own_arithmetic():
    """A 20 stake here is what a book calls '10 each way'."""
    r = core.compute_each_way(20.0, 9.0, 0.2)
    assert approx(r.win_return, 10 * 9 + 10 * (1 + 8 * 0.2))
    assert approx(r.place_return, 10 * (1 + 8 * 0.2))


def test_place_terms_change_the_place_leg_only():
    win_legs = []
    for terms, expected_place_odds in (("1/2", 5.0), ("1/4", 3.0), ("1/5", 2.6)):
        r = core.compute_each_way(10.0, 9.0, core.parse_place_terms(terms))
        assert approx(r.place_odds, expected_place_odds)
        win_legs.append(r.win_stake * r.odds)
    assert len(set(round(w, 6) for w in win_legs)) == 1   # win half untouched


def test_a_short_priced_each_way_can_lose_on_a_place():
    """At 2/1 with 1/5 terms, placing returns less than the outlay."""
    r = core.compute_each_way(10.0, 3.0, 0.2)
    assert approx(r.place_return, 7.00)              # 5 x 1.4
    assert r.place_profit < 0


def test_each_way_rejects_impossible_terms():
    for fraction in (0, -0.2, 1.5):
        try:
            core.compute_each_way(10.0, 3.0, fraction)
        except core.OddsError:
            pass
        else:
            raise AssertionError("expected OddsError for {}".format(fraction))


# -- arbitrage: odds 1.80 / 3.70, stake 100 --------------------------------

def test_arbitrage_reference_example():
    r = core.compute_arbitrage(1.80, 3.70, 100.0)
    assert approx(r.stake_b, 48.65)          # 100 * 1.80 / 3.70
    assert approx(r.payout_a, 180.00)
    assert approx(r.payout_b, 180.00)
    assert approx(r.total_stake, 148.65)
    assert approx(r.profit_a, 31.35)         # same on both outcomes
    assert approx(r.profit_b, 31.35)
    assert approx(r.return_a_pct, 17.42)     # profit / that outcome's payout
    assert r.is_hedged is True
    assert r.is_arbitrage is True


def test_hedge_stake_matches_the_payouts():
    assert approx(core.hedge_stake(100.0, 1.80, 3.70), 48.65)
    r = core.compute_arbitrage(2.35, 1.95, 250.0)
    assert approx(r.payout_a, r.payout_b)
    assert r.is_hedged is True


def test_unequal_stakes_are_reported_per_outcome():
    """Payouts need not match - each side gets its own profit figure."""
    r = core.compute_two_way(1.80, 3.70, 100.0, 60.0)
    assert approx(r.payout_a, 180.00)        # 100 * 1.80
    assert approx(r.payout_b, 222.00)        # 60 * 3.70
    assert approx(r.total_stake, 160.00)
    assert approx(r.profit_a, 20.00)
    assert approx(r.profit_b, 62.00)
    assert approx(r.worst_profit, 20.00)
    assert approx(r.best_profit, 62.00)
    assert r.is_hedged is False
    assert r.is_arbitrage is True            # both outcomes still clear zero
    assert approx(r.hedge_stake_b, 48.65)    # what B would be for equal payout


def test_uncovered_position_is_not_an_arbitrage():
    """Under-staking one side leaves an outcome that loses money."""
    r = core.compute_two_way(1.80, 3.70, 100.0, 10.0)
    assert approx(r.profit_a, 70.00)         # 180 - 110
    assert approx(r.profit_b, -73.00)        # 37 - 110
    assert r.is_arbitrage is False
    assert r.best_profit > 0 > r.worst_profit
    assert r.market_has_arbitrage is True    # the odds still allow one


def test_hedged_survives_rounding_the_stake_to_the_cent():
    """The auto-sized stake is rounded for display; that still counts as hedged."""
    r = core.compute_two_way(5.00, 3.70, 100.0, 135.14)   # exact is 135.1351...
    assert r.is_hedged is True
    assert not approx(r.payout_a, r.payout_b, tol=0.005)  # payouts differ by 2c


def test_equal_payout_maximises_the_worst_case():
    even = core.compute_arbitrage(1.80, 3.70, 100.0)
    for stake_b in (30.0, 40.0, 48.0, 50.0, 60.0, 80.0):
        skewed = core.compute_two_way(1.80, 3.70, 100.0, stake_b)
        assert skewed.worst_profit <= even.worst_profit + 0.005


def test_no_arbitrage_locks_in_a_loss():
    r = core.compute_arbitrage(1.90, 1.90, 100.0)   # implied 105.26%
    assert r.is_arbitrage is False
    assert r.market_has_arbitrage is False
    assert r.profit_a < 0 and r.profit_b < 0
    assert approx(r.implied_total_pct, 105.263)


def test_arbitrage_rejects_bad_odds():
    for bad in ((1.0, 2.0), (2.0, 0.5)):
        try:
            core.compute_arbitrage(bad[0], bad[1], 100)
        except core.OddsError:
            pass
        else:
            raise AssertionError("expected OddsError for {}".format(bad))


# -- expected value: $100 at +110 with a fair 50% --------------------------

def test_ev_reference_example():
    odds = core.american_to_decimal(110)
    r = core.compute_ev(100.0, odds, 0.50)
    assert approx(r.profit_if_win, 110.00)
    assert approx(r.expected_value, 5.00)    # 0.50 x 110 - 0.50 x 100
    assert approx(r.ev_pct, 5.00)


def test_ev_coin_flip_at_even_money_is_zero():
    r = core.compute_ev(100.0, 2.00, 0.50)
    assert approx(r.expected_value, 0.00)


def test_ev_screenshot_defaults():
    r = core.compute_ev(100.0, 2.20, 0.60)
    assert approx(r.expected_value, 32.00)   # 0.60 x 120 - 0.40 x 100
    assert approx(r.break_even_probability, 0.454545)
    assert approx(r.edge_pct, 14.5454)


def test_ev_negative_when_underpriced():
    r = core.compute_ev(100.0, 1.80, 0.50)
    assert r.expected_value < 0
    assert approx(r.expected_value, -10.00)


def test_ev_rejects_impossible_probability():
    try:
        core.compute_ev(100.0, 2.0, 1.4)
    except core.OddsError:
        pass
    else:
        raise AssertionError("expected OddsError for p > 1")


# -- parsing ---------------------------------------------------------------

def test_parse_odds_formats():
    assert approx(core.parse_odds("2.20", core.DECIMAL), 2.20)
    assert approx(core.parse_odds("+110", core.AMERICAN), 2.10)
    assert approx(core.parse_odds("-105", core.AMERICAN), 1.95238)


def test_parse_amount_strips_symbols():
    assert approx(core.parse_amount("$1,250.50", "Stake"), 1250.50)


# -- storage ---------------------------------------------------------------

def test_store_save_rename_delete(tmp_path=None):
    import tempfile
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "bets.json")

    store = BetStore(path)
    assert len(store) == 0

    r = core.compute_arbitrage(1.80, 3.70, 100.0)
    bet = store.add("Rams / Niners", ARBITRAGE, {"odds_a": "1.80"}, r.as_dict())
    assert len(store) == 1

    assert store.rename(bet["id"], "Sunday hedge") is True
    reloaded = BetStore(path)
    assert reloaded.get(bet["id"])["name"] == "Sunday hedge"

    assert reloaded.delete(bet["id"]) is True
    assert len(BetStore(path)) == 0


def _run():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL  {}: {}".format(name, exc))
        else:
            print("pass  {}".format(name))
    print("\n{} passed, {} failed".format(len(tests) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run())
