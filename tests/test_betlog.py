"""The shared log schema and the CSV export.

Runs standalone (``python tests/test_betlog.py``) or under pytest.
"""

import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta  # noqa: E402

from betting_calc import betlog, core  # noqa: E402
from betting_calc.storage import ARBITRAGE, EV, MANUAL, BetStore  # noqa: E402


def approx(a, b, tol=0.005):
    return abs(a - b) < tol


def make_store():
    store = BetStore(os.path.join(tempfile.mkdtemp(), "bets.json"))
    arb = core.compute_arbitrage(1.80, 3.70, 100.0)
    store.add("Rams hedge", ARBITRAGE,
              {"odds_format": core.FRACTIONAL, "odds_a": "4/5",
               "odds_b": "27/10", "stake_a": "100", "stake_b": "48.65"},
              arb.as_dict())
    ev = core.compute_ev(50.0, 3.40, 0.34)
    store.add("Scheffler top-5", EV,
              {"odds_format": core.DECIMAL, "odds": "3.40", "wager": "50",
               "win_prob": "34"}, ev.as_dict())
    manual = {"selection": "Ireland -1.5", "event": "Six Nations",
              "bookmaker": "Paddy Power", "odds": "5/4", "stake": "40",
              "payout": "90", "date": "2026-08-20", "notes": "gut call",
              "odds_format": core.FRACTIONAL}
    store.add("Ireland handicap", MANUAL, manual,
              betlog.manual_results("40", "90"), status="Won")
    return store


# -- schema ----------------------------------------------------------------

def test_every_kind_produces_the_same_columns():
    store = make_store()
    for bet in store.all():
        row = betlog.log_row(bet)
        assert tuple(row.keys()) == betlog.ALL_KEYS


def test_arbitrage_row_reports_the_guaranteed_numbers():
    store = make_store()
    bet = next(b for b in store.all() if b["kind"] == ARBITRAGE)
    row = betlog.log_row(bet)
    assert row["Type"] == "Arbitrage"
    assert row["Selection"] == "Rams hedge"      # the name identifies it
    assert row["Odds"] == "4/5 / 27/10"          # the bet's own format
    assert approx(row["Stake"], 148.65)
    assert approx(row["Payout"], 180.00)         # the smaller of the two
    assert approx(row["Projected P/L"], 31.35)   # worst case
    assert row["Status"] == "Pending"


def test_ev_row_reports_stake_return_and_ev():
    store = make_store()
    bet = next(b for b in store.all() if b["kind"] == EV)
    row = betlog.log_row(bet)
    assert row["Type"] == "Expected Value"
    assert row["Odds"] == "3.40"
    assert approx(row["Stake"], 50.00)
    assert approx(row["Payout"], 170.00)         # 50 x 3.40
    assert approx(row["Projected P/L"], 7.80)    # 0.34 x 120 - 0.66 x 50


def test_selection_falls_back_to_the_name():
    """Selection is the row's identifier, so it is never left blank."""
    typed = betlog.log_row({
        "name": "Saturday double", "kind": MANUAL, "status": "Pending",
        "created": "2026-08-23T10:00:00",
        "inputs": {"selection": "Home win + over 2.5", "stake": "34.55"},
        "results": betlog.manual_results("34.55", "")})
    assert typed["Selection"] == "Home win + over 2.5"

    blank = betlog.log_row({
        "name": "Weekend treble", "kind": MANUAL, "status": "Pending",
        "created": "2026-08-23T10:00:00",
        "inputs": {"selection": "", "stake": "40"},
        "results": betlog.manual_results("40", "")})
    assert blank["Selection"] == "Weekend treble"   # not blank, not a dash
    assert blank["Name"] == "Weekend treble"        # the name itself is untouched


def test_a_calculated_bet_without_a_name_keeps_a_descriptor():
    for kind, expected in ((ARBITRAGE, "Both sides (hedge)"),
                           (EV, "Single wager")):
        row = betlog.log_row({"name": "", "kind": kind, "status": "Pending",
                              "created": "2026-08-23T10:00:00",
                              "inputs": {}, "results": {}})
        assert row["Selection"] == expected


def test_manual_row_keeps_what_was_typed():
    store = make_store()
    bet = next(b for b in store.all() if b["kind"] == MANUAL)
    row = betlog.log_row(bet)
    assert row["Type"] == "Manual"
    assert row["Selection"] == "Ireland -1.5"
    assert row["Event"] == "Six Nations"
    assert row["Bookmaker"] == "Paddy Power"
    assert row["Odds"] == "5/4"
    assert approx(row["Stake"], 40.00)
    assert approx(row["Payout"], 90.00)
    assert approx(row["Projected P/L"], 50.00)   # payout - stake
    assert approx(row["Realised P/L"], 50.00)    # it won, so it returned it
    assert approx(row["P/L"], 50.00)
    assert row["Date"] == "2026-08-20"           # the date entered, not saved
    assert row["Status"] == "Won"


def test_manual_bet_tolerates_blank_fields():
    """'Any bet at all' - only the name is required."""
    row = betlog.log_row({
        "name": "Pub bet", "kind": MANUAL, "status": "Pending",
        "created": "2026-08-23T10:00:00",
        "inputs": {"selection": "", "stake": "", "payout": ""},
        "results": betlog.manual_results("", ""),
    })
    assert row["Name"] == "Pub bet"
    assert row["Stake"] is None and row["Payout"] is None
    assert row["Projected P/L"] is None
    assert row["Date"] == "2026-08-23"
    assert betlog.csv_cell(row["Stake"]) == ""


def test_suggested_payout_follows_the_odds_format():
    assert approx(betlog.suggested_payout("5/4", "40", core.FRACTIONAL), 90.00)
    assert approx(betlog.suggested_payout("2.25", "40", core.DECIMAL), 90.00)
    assert approx(betlog.suggested_payout("+125", "40", core.AMERICAN), 90.00)
    assert betlog.suggested_payout("nonsense", "40", core.DECIMAL) is None
    assert betlog.suggested_payout("2.0", "", core.DECIMAL) is None


# -- totals ----------------------------------------------------------------

def test_a_lost_bet_costs_its_stake():
    """Nothing used to be recorded on a loss; it must show as -stake."""
    row = betlog.log_row({
        "name": "Losing single", "kind": MANUAL, "status": "Lost",
        "created": "2026-08-23T10:00:00",
        "inputs": {"selection": "Match winner", "odds": "20/23", "stake": "25",
                   "payout": ""},
        "results": betlog.manual_results("25", ""),
    })
    assert approx(row["Realised P/L"], -25.00)
    assert approx(row["P/L"], -25.00)


def test_a_void_bet_is_a_wash():
    row = betlog.log_row({
        "name": "Rained off", "kind": MANUAL, "status": "Void",
        "created": "2026-08-23T10:00:00",
        "inputs": {"stake": "25", "payout": "90"},
        "results": betlog.manual_results("25", "90"),
    })
    assert row["Realised P/L"] == 0.0
    assert row["P/L"] == 0.0


def test_a_pending_bet_still_shows_the_projection():
    row = betlog.log_row({
        "name": "Open", "kind": MANUAL, "status": "Pending",
        "created": "2026-08-23T10:00:00",
        "inputs": {"stake": "25", "payout": "90"},
        "results": betlog.manual_results("25", "90"),
    })
    assert row["Realised P/L"] is None
    assert approx(row["P/L"], 65.00)


def _manual(status, odds="", stake="", payout="", fmt=core.FRACTIONAL):
    return {"name": "x", "kind": MANUAL, "status": status,
            "created": "2026-08-23T12:00:00",
            "inputs": {"odds": odds, "stake": stake, "payout": payout,
                       "odds_format": fmt},
            "results": betlog.manual_results(stake, payout)}


def test_a_winner_with_no_payout_falls_back_to_the_odds():
    """8/11 on 20 returns 34.55, so the win is worth 14.55."""
    row = betlog.log_row(_manual("Won", odds="8/11", stake="20"))
    assert approx(row["Payout"], 34.55)
    assert approx(row["Realised P/L"], 14.55)
    assert approx(row["P/L"], 14.55)


def test_odds_saved_under_the_wrong_format_still_derive_a_payout():
    """8/11 stored as 'decimal' - the text is the better evidence."""
    bet = _manual("Won", odds="8/11", stake="20", fmt=core.DECIMAL)
    row = betlog.log_row(bet)
    assert approx(row["Payout"], 34.55)
    assert approx(row["P/L"], 14.55)


def test_a_typed_payout_beats_the_derived_one():
    """A boost or partial cash-out is whatever you say it is."""
    row = betlog.log_row(_manual("Won", odds="7/5", stake="40", payout="150"))
    assert approx(row["Payout"], 150.00)      # not 40 x 2.4 = 96
    assert approx(row["P/L"], 110.00)


def test_deriving_the_payout_does_not_change_a_loss():
    row = betlog.log_row(_manual("Lost", odds="2/1", stake="25"))
    assert approx(row["Payout"], 75.00)       # what it would have returned
    assert approx(row["P/L"], -25.00)         # but it lost, so -stake


def test_a_pending_bet_projects_from_the_odds():
    row = betlog.log_row(_manual("Pending", odds="2/1", stake="25"))
    assert approx(row["Projected P/L"], 50.00)
    assert approx(row["P/L"], 50.00)


def test_no_odds_and_no_payout_stays_blank():
    row = betlog.log_row(_manual("Won", stake="20"))
    assert row["Payout"] is None
    assert row["P/L"] is None


def test_derived_payout_follows_the_bets_odds_format():
    for fmt, odds in ((core.DECIMAL, "1.7273"), (core.AMERICAN, "-137"),
                      (core.FRACTIONAL, "8/11")):
        row = betlog.log_row(_manual("Won", odds=odds, stake="20", fmt=fmt))
        assert approx(row["Payout"], 34.55, tol=0.05), (fmt, row["Payout"])


def test_realised_pl_rules():
    assert betlog.realised_pl(40.0, 96.0, "Won") == 56.0
    assert betlog.realised_pl(25.0, None, "Lost") == -25.0
    assert betlog.realised_pl(25.0, 90.0, "Void") == 0.0
    assert betlog.realised_pl(25.0, 90.0, "Pending") is None
    # a win with no payout recorded cannot be worked out
    assert betlog.realised_pl(25.0, None, "Won") is None
    assert betlog.realised_pl(None, None, "Lost") is None


def test_totals_keep_open_and_settled_apart():
    figures = betlog.totals(make_store().all())
    assert figures["count"] == 3
    assert approx(figures["staked"], 148.65 + 50.00 + 40.00)
    # the two calculated bets are still open, the manual one won
    assert figures["open_count"] == 2
    assert approx(figures["projected"], 31.35 + 7.80)
    assert figures["settled_count"] == 1
    assert approx(figures["settled"], 50.00)
    assert approx(figures["settled_stake"], 40.00)
    assert approx(figures["roi_pct"], 125.00)


def test_totals_for_one_winner_and_two_losers():
    """A settled day: the winner has to cover both losing stakes."""
    bets = [
        {"name": "Bet one", "kind": MANUAL, "status": "Won",
         "created": "2026-08-23T10:00:00",
         "inputs": {"stake": "40", "payout": "96"},
         "results": betlog.manual_results("40", "96")},
        {"name": "Bet two", "kind": MANUAL, "status": "Lost",
         "created": "2026-08-23T10:00:00",
         "inputs": {"stake": "25", "payout": ""},
         "results": betlog.manual_results("25", "")},
        {"name": "Bet three", "kind": MANUAL, "status": "Lost",
         "created": "2026-08-23T10:00:00",
         "inputs": {"stake": "10.95", "payout": ""},
         "results": betlog.manual_results("10.95", "")},
    ]
    rows = [betlog.log_row(b) for b in bets]
    assert approx(rows[0]["P/L"], 56.00)
    assert approx(rows[1]["P/L"], -25.00)
    assert approx(rows[2]["P/L"], -10.95)

    figures = betlog.totals(bets)
    assert approx(figures["staked"], 75.95)
    assert approx(figures["settled"], 20.05)      # 56 - 25 - 10.95
    assert figures["open_count"] == 0
    assert approx(figures["roi_pct"], 26.4, tol=0.05)


# -- date periods ----------------------------------------------------------

def test_periods_select_the_right_windows():
    today = date(2026, 8, 23)
    def day(n):
        return (today - timedelta(days=n)).isoformat()

    assert betlog.in_period(day(0), "today", today) is True
    assert betlog.in_period(day(1), "today", today) is False

    assert betlog.in_period(day(6), "7", today) is True
    assert betlog.in_period(day(7), "7", today) is False
    assert betlog.in_period(day(29), "30", today) is True
    assert betlog.in_period(day(30), "30", today) is False

    assert betlog.in_period("2026-08-01", "month", today) is True
    assert betlog.in_period("2026-07-31", "month", today) is False
    assert betlog.in_period("2026-01-01", "year", today) is True
    assert betlog.in_period("2025-12-31", "year", today) is False


def test_all_time_keeps_everything_including_unreadable_dates():
    today = date(2026, 8, 23)
    assert betlog.in_period("not a date", "all", today) is True
    assert betlog.in_period("", "all", today) is True
    # a dated view cannot place an unreadable date, so it drops out
    assert betlog.in_period("not a date", "30", today) is False


def test_a_future_dated_bet_is_not_in_a_trailing_window():
    today = date(2026, 8, 23)
    assert betlog.in_period("2026-09-01", "30", today) is False
    assert betlog.in_period("2026-09-01", "all", today) is True


def test_parse_date_reads_iso_only():
    assert betlog.parse_date("2026-08-20") == date(2026, 8, 20)
    assert betlog.parse_date("2026-08-20T10:00:00") == date(2026, 8, 20)
    assert betlog.parse_date("20/08/2026") is None
    assert betlog.parse_date("") is None
    assert betlog.parse_date(None) is None


# -- csv -------------------------------------------------------------------

def test_csv_has_a_header_and_one_row_per_bet():
    store = make_store()
    path = os.path.join(tempfile.mkdtemp(), betlog.default_filename())
    written = betlog.export_csv(store.all(), path)
    assert written == 3

    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == list(betlog.CSV_COLUMNS)
    assert len(rows) == 4
    assert {r[2] for r in rows[1:]} == {"Arbitrage", "Expected Value", "Manual"}


def test_csv_numbers_are_plain_so_spreadsheets_parse_them():
    store = make_store()
    path = os.path.join(tempfile.mkdtemp(), "log.csv")
    betlog.export_csv(store.all(), path)
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for column in ("Stake", "Payout", "Projected P/L", "Realised P/L"):
            if row[column]:
                float(row[column])          # raises if it is not a bare number
                assert "$" not in row[column] and "," not in row[column]


def test_csv_is_written_with_a_bom_for_excel():
    path = os.path.join(tempfile.mkdtemp(), "log.csv")
    betlog.export_csv(make_store().all(), path)
    with open(path, "rb") as fh:
        assert fh.read(3) == b"\xef\xbb\xbf"


def test_failed_export_leaves_no_partial_file():
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "log.csv")
    betlog.export_csv(make_store().all(), path)
    before = os.path.getsize(path)

    # Fail part-way through writing, once the temp file already has content.
    original, calls = betlog.csv_cell, []

    def flaky(value):
        calls.append(value)
        if len(calls) > 6:
            raise RuntimeError("boom")
        return original(value)

    betlog.csv_cell = flaky
    try:
        betlog.export_csv(make_store().all(), path)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the injected failure to propagate")
    finally:
        betlog.csv_cell = original

    assert os.path.getsize(path) == before, "existing export must survive"
    leftovers = [f for f in os.listdir(directory) if f.endswith(".tmp")]
    assert not leftovers, "temp file should be cleaned up"


def test_export_of_an_empty_log_still_writes_the_header():
    path = os.path.join(tempfile.mkdtemp(), "empty.csv")
    assert betlog.export_csv([], path) == 0
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        assert list(csv.reader(fh)) == [list(betlog.CSV_COLUMNS)]


# -- storage ---------------------------------------------------------------

def test_status_round_trips_to_disk():
    store = make_store()
    bet = store.all()[0]
    assert store.set_status(bet["id"], "Void") is True
    assert store.set_status(bet["id"], "Nonsense") is False
    assert BetStore(store.path).get(bet["id"])["status"] == "Void"


def test_old_records_without_a_status_load_as_pending():
    import json
    path = os.path.join(tempfile.mkdtemp(), "legacy.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump([{"id": "abc", "name": "Old bet", "kind": ARBITRAGE,
                    "created": "2026-01-01T00:00:00", "inputs": {},
                    "results": {}}], fh)
    assert BetStore(path).get("abc")["status"] == "Pending"


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
