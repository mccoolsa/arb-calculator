"""Tkinter interface for the arbitrage and expected value calculators."""

from __future__ import annotations

import os
import tkinter as tk
from datetime import date as _date
from tkinter import filedialog

from . import betlog
from . import core
from . import theme as T
from . import widgets as W
from . import __version__
from .storage import (ARBITRAGE, DEFAULT_STATUS, EV, MANUAL, STATUSES,
                      BetStore)

APP_TITLE = "Bet Lab"

#: Tab key for the log; not a bet kind, so it lives outside storage.
LOG = "log"


# ==========================================================================
# Small shared pieces
# ==========================================================================

class Stat(tk.Frame):
    """A label-over-value block, as used in the results strip."""

    def __init__(self, master, caption, value="--", value_fg=T.TEXT,
                 value_font=None, anchor="w"):
        super().__init__(master, bg=master.cget("bg"))
        self._caption = tk.Label(self, text=caption, bg=self.cget("bg"),
                                 fg=T.MUTED, font=T.FONT_SM, anchor=anchor)
        self._caption.pack(fill="x")
        self._value = tk.Label(self, text=value, bg=self.cget("bg"),
                               fg=value_fg, font=value_font or T.FONT_STAT,
                               anchor=anchor)
        self._value.pack(fill="x", pady=(3, 0))

    def set(self, value, fg=None, caption=None):
        self._value.configure(text=value)
        if fg:
            self._value.configure(fg=fg)
        if caption is not None:
            self._caption.configure(text=caption)


class TextPrompt(tk.Toplevel):
    """Modal single-line text prompt, used for naming and renaming bets."""

    def __init__(self, parent, title, prompt, initial="", ok_text="Save"):
        super().__init__(parent, bg=T.BG)
        self.result = None
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.configure(padx=0, pady=0)

        card = W.Card(self, bg=T.CARD, outline=T.BORDER, padding=22,
                      parent_bg=T.BG)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        body = card.body

        tk.Label(body, text=title, bg=T.CARD, fg=T.TEXT,
                 font=T.FONT_H2, anchor="w").pack(fill="x")
        tk.Label(body, text=prompt, bg=T.CARD, fg=T.MUTED, font=T.FONT_SM,
                 anchor="w", justify="left", wraplength=340).pack(
                     fill="x", pady=(4, 14))

        self.var = tk.StringVar(value=initial)
        border = tk.Frame(body, bg=T.ACCENT, padx=1, pady=1)
        border.pack(fill="x")
        self.entry = tk.Entry(border, textvariable=self.var, bg=T.FIELD,
                              fg=T.TEXT, font=T.FONT, relief="flat", bd=0,
                              insertbackground=T.ACCENT, width=38,
                              highlightthickness=0,
                              selectbackground=T.ACCENT_DIM)
        self.entry.pack(fill="x", ipady=7, padx=8)

        row = tk.Frame(body, bg=T.CARD)
        row.pack(fill="x", pady=(16, 0))
        W.Button(row, "Cancel", command=self._cancel, kind="ghost",
                 width=92).pack(side="right", padx=(8, 0))
        W.Button(row, ok_text, command=self._ok, kind="primary",
                 width=110).pack(side="right")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._centre_on(parent)
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.grab_set()
        self.wait_window(self)

    def _centre_on(self, parent):
        w, h = self.winfo_width(), self.winfo_height()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        self.geometry("+{}+{}".format(max(x, 0), max(y, 0)))

    def _ok(self):
        text = self.var.get().strip()
        if text:
            self.result = text
            self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class ConfirmPrompt(tk.Toplevel):
    """Modal yes/no confirmation."""

    def __init__(self, parent, title, message, ok_text="Delete"):
        super().__init__(parent, bg=T.BG)
        self.result = False
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        card = W.Card(self, bg=T.CARD, outline=T.BORDER, padding=22,
                      parent_bg=T.BG)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        body = card.body

        tk.Label(body, text=title, bg=T.CARD, fg=T.TEXT, font=T.FONT_H2,
                 anchor="w").pack(fill="x")
        tk.Label(body, text=message, bg=T.CARD, fg=T.TEXT_DIM, font=T.FONT,
                 anchor="w", justify="left", wraplength=340).pack(
                     fill="x", pady=(6, 0))

        row = tk.Frame(body, bg=T.CARD)
        row.pack(fill="x", pady=(18, 0))
        W.Button(row, "Cancel", command=self._cancel, kind="ghost",
                 width=92).pack(side="right", padx=(8, 0))
        W.Button(row, ok_text, command=self._ok, kind="danger",
                 width=110).pack(side="right")

        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry("+{}+{}".format(max(x, 0), max(y, 0)))
        self.grab_set()
        self.wait_window(self)

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class CalculatorPanel(tk.Frame):
    """Shared plumbing for the two calculators."""

    kind = ""

    def __init__(self, master, on_save, on_status):
        super().__init__(master, bg=T.BG)
        self._on_save = on_save
        self._on_status = on_status
        self._odds_format = core.DECIMAL
        self._odds_fields = []
        self.result = None
        self._suspend = False

    # -- helpers ----------------------------------------------------------

    def _watch(self, *variables):
        for var in variables:
            var.trace_add("write", lambda *_: self.recalculate())

    def _format_toggle(self, parent):
        holder = tk.Frame(parent, bg=parent.cget("bg"))
        tk.Label(holder, text="Odds format", bg=holder.cget("bg"), fg=T.MUTED,
                 font=T.FONT_SM).pack(side="left", padx=(0, 8))
        seg = W.SegmentedControl(
            holder,
            [(core.DECIMAL, "Decimal"), (core.AMERICAN, "American"),
             (core.FRACTIONAL, "Fractional")],
            command=self._change_format, bg=holder.cget("bg"),
            font=T.FONT_SM, padx=11, pady=4,
        )
        seg.pack(side="left")
        return holder

    @staticmethod
    def _configure_odds_field(field, fmt):
        """Point a field's steppers at the right increment for the format."""
        if fmt == core.AMERICAN:
            # No legal prices between -100 and +100, so step over the gap.
            field.set_custom_step(None)
            field.set_step(5, 0)
            field.set_bounds(None, None, forbidden=(-100, 100))
        elif fmt == core.FRACTIONAL:
            field.set_custom_step(core.step_fractional)
            field.set_bounds(None, None, forbidden=None)
        else:
            field.set_custom_step(None)
            field.set_step(0.05, 2)
            field.set_bounds(1.01, None, forbidden=None)

    def _apply_odds_format(self, fmt, convert_from=None):
        """Re-point the odds fields, optionally rewriting their values."""
        self._odds_format = fmt
        for var, field in self._odds_fields:
            self._configure_odds_field(field, fmt)
            if convert_from is None:
                continue
            try:
                var.set(core.format_odds(
                    core.parse_odds(var.get(), convert_from), fmt))
            except core.OddsError:
                pass    # leave unparseable text alone for the user to fix

    def _change_format(self, fmt):
        previous = self._odds_format
        if previous == fmt:
            return
        self._suspend = True
        self._apply_odds_format(fmt, convert_from=previous)
        self._suspend = False
        self.recalculate()

    def recalculate(self):
        if self._suspend:
            return
        try:
            self.result = self._compute()
        except core.OddsError as exc:
            self.result = None
            self._show_error(str(exc))
        else:
            self._show_result(self.result)

    # -- to implement -----------------------------------------------------

    def _compute(self):
        raise NotImplementedError

    def _show_result(self, result):
        raise NotImplementedError

    def _show_error(self, message):
        raise NotImplementedError

    def snapshot(self) -> tuple[dict, dict]:
        raise NotImplementedError

    def restore(self, inputs: dict) -> None:
        raise NotImplementedError

    def default_name(self) -> str:
        raise NotImplementedError

    def summary(self, bet: dict) -> str:
        raise NotImplementedError


# ==========================================================================
# Arbitrage
# ==========================================================================

ARB_NOTES = (
    "Arbitrage (hedging) means backing every outcome of a two-way market at "
    "different books so that any result returns the same payout. It exists "
    "because books price independently — when two sides drift out of sync, "
    "the combined implied probability can fall below 100%.\n\n"
    "Both stakes are yours to set and the payouts do not have to match. Each "
    "outcome is worked out on its own — payout is stake × odds, and profit is "
    "that payout minus everything staked on both sides. The percentage beside "
    "each is profit measured against that outcome's payout. A guaranteed "
    "profit means the worse of the two outcomes still clears zero.\n\n"
    "Tick Lock Stake to pin side A: side B is then resized to stake_A × odds_A ÷ "
    "odds_B — the sizing that equalises the payouts and maximises the worst "
    "case — whenever the odds or side A change. You can still overtype side B "
    "at any time; it holds until the next change to the pinned side."
)


class ArbitragePanel(CalculatorPanel):
    kind = ARBITRAGE

    def __init__(self, master, on_save, on_status):
        super().__init__(master, on_save, on_status)

        self.odds_a = tk.StringVar(value="1.80")
        self.odds_b = tk.StringVar(value="3.70")
        self.stake_a = tk.StringVar(value="100")
        self.stake_b = tk.StringVar(value="48.65")
        self.lock_a = tk.BooleanVar(value=True)
        self.payout_a_out = tk.StringVar(value="0.00")
        self.payout_b_out = tk.StringVar(value="0.00")

        self._build()
        for name, var in (("odds_a", self.odds_a), ("odds_b", self.odds_b),
                          ("stake_a", self.stake_a), ("stake_b", self.stake_b)):
            var.trace_add("write", lambda *_, n=name: self._changed(n))
        self.recalculate()

    # -- layout -----------------------------------------------------------

    def _build(self):
        card = W.Card(self, bg=T.CARD, outline=T.BORDER_SOFT, padding=22,
                      parent_bg=T.BG)
        card.pack(fill="x")
        body = card.body

        head = tk.Frame(body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="Arbitrage calculator", bg=T.CARD, fg=T.TEXT,
                 font=T.FONT_H2).pack(side="left")
        self._format_toggle(head).pack(side="right")

        self.subtitle = tk.Label(
            body, text="", bg=T.CARD, fg=T.MUTED, font=T.FONT_SM, anchor="w")
        self.subtitle.pack(fill="x", pady=(2, 16))

        # column 0 = row label, 1 = side A, 2 = the lock, 3 = side B
        grid = tk.Frame(body, bg=T.CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1, uniform="leg")
        grid.grid_columnconfigure(3, weight=1, uniform="leg")

        tk.Label(grid, text="", bg=T.CARD).grid(row=0, column=0)
        for col, text in ((1, "Side A"), (3, "Side B")):
            tk.Label(grid, text=text, bg=T.CARD, fg=T.FAINT, font=T.FONT_SM,
                     anchor="w").grid(row=0, column=col, sticky="w",
                                      padx=(0, 10), pady=(0, 6))

        def row_label(row, text):
            tk.Label(grid, text=text, bg=T.CARD, fg=T.TEXT_DIM, font=T.FONT_LABEL,
                     anchor="w", width=8).grid(row=row, column=0, sticky="w",
                                               pady=5, padx=(0, 14))

        row_label(1, "Odds")
        self.field_odds_a = W.NumberField(grid, self.odds_a, step=0.05,
                                          minimum=1.01)
        self.field_odds_a.grid(row=1, column=1, sticky="ew", pady=5)
        self.field_odds_b = W.NumberField(grid, self.odds_b, step=0.05,
                                          minimum=1.01)
        self.field_odds_b.grid(row=1, column=3, sticky="ew", pady=5)
        self._odds_fields = [(self.odds_a, self.field_odds_a),
                             (self.odds_b, self.field_odds_b)]

        # Both stakes are always editable; the lock only decides whether
        # side B gets resized for you.
        row_label(2, "Stake")
        self.field_stake_a = W.NumberField(grid, self.stake_a, affix="$",
                                           step=5, minimum=0)
        self.field_stake_a.grid(row=2, column=1, sticky="ew", pady=5)
        self.field_stake_b = W.NumberField(grid, self.stake_b, affix="$",
                                           step=5, minimum=0)
        self.field_stake_b.grid(row=2, column=3, sticky="ew", pady=5)

        W.CheckBox(grid, "Lock Stake", self.lock_a, command=self._toggle_lock,
                   bg=T.CARD).grid(row=2, column=2, padx=12)

        row_label(3, "Payout")
        W.NumberField(grid, self.payout_a_out, affix="$", readonly=True).grid(
            row=3, column=1, sticky="ew", pady=5)
        W.NumberField(grid, self.payout_b_out, affix="$", readonly=True).grid(
            row=3, column=3, sticky="ew", pady=5)

        self._apply_lock()

        W.divider(body, pady=16)

        stats = tk.Frame(body, bg=T.CARD)
        stats.pack(fill="x")
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")
        self.stat_stake = Stat(stats, "Total Stake")
        self.stat_stake.grid(row=0, column=0, sticky="ew")
        self.stat_a = Stat(stats, "If Side A wins")
        self.stat_a.grid(row=0, column=1, sticky="ew")
        self.stat_b = Stat(stats, "If Side B wins")
        self.stat_b.grid(row=0, column=2, sticky="ew")

        self.footnote = tk.Label(body, text="", bg=T.CARD, fg=T.FAINT,
                                 font=T.FONT_SM, anchor="w")
        self.footnote.pack(fill="x", pady=(12, 0))

        self.banner = tk.Label(body, text="", bg=T.CARD, fg=T.GREEN,
                               font=T.FONT_BOLD, anchor="w")
        self.banner.pack(fill="x", pady=(10, 0))

        actions = tk.Frame(body, bg=T.CARD)
        actions.pack(fill="x", pady=(18, 0))
        self.save_button = W.Button(actions, "Save this bet",
                                    command=lambda: self._on_save(self),
                                    kind="primary", width=140)
        self.save_button.pack(side="left")
        W.Button(actions, "Reset", command=self.reset, kind="ghost",
                 width=90).pack(side="left", padx=(10, 0))

        notes = W.Card(self, bg=T.PANEL, outline=T.BORDER_SOFT, padding=20,
                       parent_bg=T.BG)
        notes.pack(fill="x", pady=(16, 0))
        tk.Label(notes.body, text="How this is calculated", bg=T.PANEL,
                 fg=T.TEXT, font=T.FONT_H3, anchor="w").pack(fill="x")
        tk.Label(notes.body, text=ARB_NOTES, bg=T.PANEL, fg=T.TEXT_DIM,
                 font=T.FONT_SM, anchor="w", justify="left",
                 wraplength=620).pack(fill="x", pady=(8, 0))

    # -- behaviour --------------------------------------------------------

    # -- stake lock -------------------------------------------------------

    def _toggle_lock(self):
        """Lock Stake pins side A and keeps side B sized for an equal payout."""
        self._apply_lock()
        if self.lock_a.get():
            self._autosize_b()
        self.recalculate()

    def _apply_lock(self):
        locked = self.lock_a.get()
        self.field_stake_a.set_pinned(locked)
        self.subtitle.configure(
            text="Two-way market — both stakes are yours to set.   "
                 + ("Side A is pinned, so side B is resized for an equal "
                    "payout whenever the odds or side A change."
                    if locked else
                    "Payouts need not match; tick Lock Stake to auto-size "
                    "side B."))

    def _autosize_b(self):
        """Resize side B so both payouts match. Silent if inputs are junk."""
        try:
            odds_a = core.parse_odds(self.odds_a.get(), self._odds_format)
            odds_b = core.parse_odds(self.odds_b.get(), self._odds_format)
            stake_a = core.parse_amount(self.stake_a.get(), "Stake")
        except core.OddsError:
            return
        self._suspend = True
        try:
            self.stake_b.set("{:,.2f}".format(
                core.hedge_stake(stake_a, odds_a, odds_b)))
        finally:
            self._suspend = False

    def _changed(self, source):
        if self._suspend:
            return
        if self.lock_a.get() and source != "stake_b":
            self._autosize_b()
        self.recalculate()

    # -- calculation ------------------------------------------------------

    def reset(self):
        self._suspend = True
        fmt = self._odds_format
        self.odds_a.set(core.format_odds(1.80, fmt))
        self.odds_b.set(core.format_odds(3.70, fmt))
        self.stake_a.set("100")
        self.lock_a.set(True)
        self._apply_lock()
        self._suspend = False
        self._autosize_b()
        self.recalculate()

    def _compute(self):
        odds_a = core.parse_odds(self.odds_a.get(), self._odds_format)
        odds_b = core.parse_odds(self.odds_b.get(), self._odds_format)
        stake_a = core.parse_amount(self.stake_a.get(), "Side A stake")
        stake_b = core.parse_amount(self.stake_b.get(), "Side B stake")
        return core.compute_two_way(odds_a, odds_b, stake_a, stake_b)

    @staticmethod
    def _signed(value):
        return ("+" if value >= 0 else "") + core.money(value)

    def _show_result(self, r):
        self.payout_a_out.set("{:,.2f}".format(r.payout_a))
        self.payout_b_out.set("{:,.2f}".format(r.payout_b))

        self.stat_stake.set(core.money(r.total_stake))
        for stat, profit, ret, side in ((self.stat_a, r.profit_a, r.return_a_pct, "A"),
                                        (self.stat_b, r.profit_b, r.return_b_pct, "B")):
            stat.set(self._signed(profit),
                     fg=T.GREEN if profit > 0 else (T.RED if profit < 0 else T.TEXT),
                     caption="If Side {} wins ({})".format(side, core.pct(ret)))

        footnote = ("Return on total stake {} / {}   ·   combined implied "
                    "probability {}".format(core.pct(r.roi_a_pct),
                                            core.pct(r.roi_b_pct),
                                            core.pct(r.implied_total_pct)))
        if not r.is_hedged:
            footnote += ("   ·   equal payout at side B = "
                         + core.money(r.hedge_stake_b))
        self.footnote.configure(text=footnote)

        if r.is_arbitrage:
            self.banner.configure(
                text="✓  Guaranteed profit — worst case {}"
                     .format(self._signed(r.worst_profit)), fg=T.GREEN)
        elif r.best_profit > 0:
            loser = "Side A" if r.profit_a < r.profit_b else "Side B"
            self.banner.configure(
                text="◐  Not covered — {} winning costs you {}"
                     .format(loser, core.money(abs(r.worst_profit))), fg=T.AMBER)
        else:
            self.banner.configure(
                text="✕  Both outcomes lose — worst case {}"
                     .format(self._signed(r.worst_profit)), fg=T.RED)
        self.save_button.set_enabled(True)

    def _show_error(self, message):
        for var in (self.payout_a_out, self.payout_b_out):
            var.set("--")
        self.stat_stake.set("--", fg=T.TEXT)
        self.stat_a.set("--", fg=T.TEXT, caption="If Side A wins")
        self.stat_b.set("--", fg=T.TEXT, caption="If Side B wins")
        self.footnote.configure(text="")
        self.banner.configure(text="⚠  " + message, fg=T.AMBER)
        self.save_button.set_enabled(False)

    def snapshot(self):
        r = self.result
        inputs = {
            "odds_format": self._odds_format,
            "odds_a": self.odds_a.get(),
            "odds_b": self.odds_b.get(),
            "stake_a": self.stake_a.get(),
            "stake_b": self.stake_b.get(),
            "lock_a": self.lock_a.get(),
        }
        return inputs, (r.as_dict() if r else {})

    def restore(self, inputs):
        self._suspend = True
        fmt = inputs.get("odds_format", core.DECIMAL)
        if fmt != self._odds_format:
            self.format_control.set(fmt)
            self._apply_odds_format(fmt)    # values come from the saved bet
        self.odds_a.set(inputs.get("odds_a", "1.80"))
        self.odds_b.set(inputs.get("odds_b", "3.70"))
        self.lock_a.set(bool(inputs.get("lock_a", True)))
        self._apply_lock()
        self.stake_a.set(inputs.get("stake_a", "100"))
        self.stake_b.set(inputs.get("stake_b", "48.65"))
        self._suspend = False
        self.recalculate()

    def default_name(self):
        r = self.result
        if not r:
            return "Arbitrage bet"
        return "Arb {:.2f} / {:.2f}".format(r.odds_a, r.odds_b)

    @staticmethod
    def summary(bet):
        r = bet.get("results") or {}
        if not r:
            return "no result stored"
        worst = r.get("worst_profit", r.get("profit", 0))
        fmt = (bet.get("inputs") or {}).get("odds_format", core.DECIMAL)
        return "{} / {}  ·  {} staked  ·  {} worst case".format(
            core.format_odds(r.get("odds_a", 2.0), fmt),
            core.format_odds(r.get("odds_b", 2.0), fmt),
            core.money(r.get("total_stake", 0)),
            ("+" if worst >= 0 else "") + core.money(worst))


# ==========================================================================
# Expected value
# ==========================================================================

EV_NOTES = (
    "Expected value is your average profit per bet if the same wager were "
    "repeated indefinitely at those odds.\n\n"
    "EV = (fair win probability × profit if the bet wins) − "
    "(fair loss probability × stake).\n\n"
    "The win probability should be a fair, no-vig number — either from your "
    "own model or devigged from the sharpest book you can find. Worked "
    "example: $100 at +110 (2.10 decimal, 11/10) with a fair 50% chance gives "
    "0.50 × $110 − 0.50 × $100 = $5.00. Anything above zero is a bet worth "
    "taking repeatedly; anything below is the book taking your money slowly.\n\n"
    "Odds can be entered as decimal, American or fractional — switching format "
    "rewrites what is on screen without changing the price."
)


class EVPanel(CalculatorPanel):
    kind = EV

    def __init__(self, master, on_save, on_status):
        super().__init__(master, on_save, on_status)

        self.wager = tk.StringVar(value="100")
        self.odds = tk.StringVar(value="2.20")
        self.win_prob = tk.StringVar(value="60")

        self._build()
        self._watch(self.wager, self.odds, self.win_prob)
        self.recalculate()

    def _build(self):
        card = W.Card(self, bg=T.CARD, outline=T.BORDER_SOFT, padding=22,
                      parent_bg=T.BG)
        card.pack(fill="x")
        body = card.body

        head = tk.Frame(body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="Expected value calculator", bg=T.CARD, fg=T.TEXT,
                 font=T.FONT_H2).pack(side="left")
        self._format_toggle(head).pack(side="right")

        tk.Label(body, text="Your profit margin over the book on a single wager",
                 bg=T.CARD, fg=T.MUTED, font=T.FONT_SM, anchor="w").pack(
                     fill="x", pady=(2, 16))

        grid = tk.Frame(body, bg=T.CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, minsize=250, weight=0)
        grid.grid_columnconfigure(2, weight=1)   # spacer keeps fields compact

        def row(index, text, field):
            tk.Label(grid, text=text, bg=T.CARD, fg=T.TEXT_DIM,
                     font=T.FONT_LABEL, anchor="w", width=15).grid(
                         row=index, column=0, sticky="w", pady=6, padx=(0, 14))
            field.grid(row=index, column=1, sticky="ew", pady=6)

        row(0, "Wager", W.NumberField(grid, self.wager, affix="$", step=5,
                                      minimum=0, on_change=self.recalculate))
        self.field_odds = W.NumberField(grid, self.odds, step=0.05, minimum=1.01,
                                        on_change=self.recalculate)
        row(1, "Odds", self.field_odds)
        self._odds_fields = [(self.odds, self.field_odds)]
        row(2, "Win probability",
            W.NumberField(grid, self.win_prob, affix="%", affix_side="right",
                          step=1, minimum=0, maximum=100,
                          on_change=self.recalculate))

        W.divider(body, pady=18)

        hero = tk.Frame(body, bg=T.CARD)
        hero.pack(fill="x")
        tk.Label(hero, text="Expected Value", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT_SM, anchor="w").pack(fill="x")
        self.hero_value = tk.Label(hero, text="--", bg=T.CARD, fg=T.TEXT,
                                   font=T.FONT_HERO, anchor="w")
        self.hero_value.pack(side="left", pady=(2, 0))
        self.hero_pct = tk.Label(hero, text="", bg=T.CARD, fg=T.MUTED,
                                 font=T.FONT_BOLD, anchor="w")
        self.hero_pct.pack(side="left", padx=(12, 0), pady=(14, 0))

        stats = tk.Frame(body, bg=T.CARD)
        stats.pack(fill="x", pady=(18, 0))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")
        self.stat_win = Stat(stats, "Profit if it wins", value_font=T.FONT_BOLD)
        self.stat_win.grid(row=0, column=0, sticky="ew")
        self.stat_lose = Stat(stats, "Loss if it loses", value_font=T.FONT_BOLD)
        self.stat_lose.grid(row=0, column=1, sticky="ew")
        self.stat_breakeven = Stat(stats, "Break-even win %",
                                   value_font=T.FONT_BOLD)
        self.stat_breakeven.grid(row=0, column=2, sticky="ew")
        self.stat_edge = Stat(stats, "Your edge", value_font=T.FONT_BOLD)
        self.stat_edge.grid(row=0, column=3, sticky="ew")

        self.banner = tk.Label(body, text="", bg=T.CARD, fg=T.GREEN,
                               font=T.FONT_BOLD, anchor="w")
        self.banner.pack(fill="x", pady=(16, 0))

        actions = tk.Frame(body, bg=T.CARD)
        actions.pack(fill="x", pady=(18, 0))
        self.save_button = W.Button(actions, "Save this bet",
                                    command=lambda: self._on_save(self),
                                    kind="primary", width=140)
        self.save_button.pack(side="left")
        W.Button(actions, "Reset", command=self.reset, kind="ghost",
                 width=90).pack(side="left", padx=(10, 0))

        notes = W.Card(self, bg=T.PANEL, outline=T.BORDER_SOFT, padding=20,
                       parent_bg=T.BG)
        notes.pack(fill="x", pady=(16, 0))
        tk.Label(notes.body, text="How this is calculated", bg=T.PANEL,
                 fg=T.TEXT, font=T.FONT_H3, anchor="w").pack(fill="x")
        tk.Label(notes.body, text=EV_NOTES, bg=T.PANEL, fg=T.TEXT_DIM,
                 font=T.FONT_SM, anchor="w", justify="left",
                 wraplength=620).pack(fill="x", pady=(8, 0))

    def reset(self):
        self._suspend = True
        self.wager.set("100")
        self.odds.set(core.format_odds(2.20, self._odds_format))
        self.win_prob.set("60")
        self._suspend = False
        self.recalculate()

    def _compute(self):
        stake = core.parse_amount(self.wager.get(), "Wager")
        odds = core.parse_odds(self.odds.get(), self._odds_format)
        prob = core.parse_amount(self.win_prob.get(), "Win probability")
        if prob > 100:
            raise core.OddsError("Win probability must be between 0% and 100%.")
        return core.compute_ev(stake, odds, prob / 100.0)

    def _show_result(self, r):
        fg = T.GREEN if r.expected_value > 0 else (
            T.RED if r.expected_value < 0 else T.TEXT)
        self.hero_value.configure(text=core.money(r.expected_value), fg=fg)
        self.hero_pct.configure(text="{} of stake".format(core.pct(r.ev_pct)), fg=fg)

        self.stat_win.set("+" + core.money(r.profit_if_win), fg=T.TEXT)
        self.stat_lose.set("-" + core.money(r.loss_if_lose), fg=T.TEXT)
        self.stat_breakeven.set(core.pct(r.break_even_probability * 100), fg=T.TEXT)
        self.stat_edge.set(("+" if r.edge_pct >= 0 else "") + core.pct(r.edge_pct),
                           fg=T.GREEN if r.edge_pct > 0 else T.RED)

        if r.expected_value > 0:
            self.banner.configure(
                text="✓  Positive EV — fair odds are {} against the {} on offer"
                     .format(core.odds_label(r.fair_odds, self._odds_format),
                             core.odds_label(r.odds, self._odds_format)),
                fg=T.GREEN)
        elif r.expected_value < 0:
            self.banner.configure(
                text="✕  Negative EV — you need {} to break even at these odds"
                     .format(core.pct(r.break_even_probability * 100)),
                fg=T.RED)
        else:
            self.banner.configure(text="—  Break-even bet, no edge either way",
                                  fg=T.MUTED)
        self.save_button.set_enabled(True)

    def _show_error(self, message):
        self.hero_value.configure(text="--", fg=T.TEXT)
        self.hero_pct.configure(text="")
        for stat in (self.stat_win, self.stat_lose, self.stat_breakeven,
                     self.stat_edge):
            stat.set("--", fg=T.TEXT)
        self.banner.configure(text="⚠  " + message, fg=T.AMBER)
        self.save_button.set_enabled(False)

    def snapshot(self):
        r = self.result
        inputs = {
            "odds_format": self._odds_format,
            "wager": self.wager.get(),
            "odds": self.odds.get(),
            "win_prob": self.win_prob.get(),
        }
        return inputs, (r.as_dict() if r else {})

    def restore(self, inputs):
        self._suspend = True
        fmt = inputs.get("odds_format", core.DECIMAL)
        if fmt != self._odds_format:
            self.format_control.set(fmt)
            self._apply_odds_format(fmt)    # values come from the saved bet
        self.wager.set(inputs.get("wager", "100"))
        self.odds.set(inputs.get("odds", "2.20"))
        self.win_prob.set(inputs.get("win_prob", "60"))
        self._suspend = False
        self.recalculate()

    def default_name(self):
        r = self.result
        if not r:
            return "EV bet"
        return "EV {:.2f} @ {:.0f}%".format(r.odds, r.win_probability * 100)

    @staticmethod
    def summary(bet):
        r = bet.get("results") or {}
        if not r:
            return "no result stored"
        fmt = (bet.get("inputs") or {}).get("odds_format", core.DECIMAL)
        return "{} at {}  ·  {:.1f}% win  ·  EV {}".format(
            core.money(r.get("stake", 0)),
            core.format_odds(r.get("odds", 2.0), fmt),
            r.get("win_probability", 0) * 100,
            ("+" if r.get("expected_value", 0) >= 0 else "")
            + core.money(r.get("expected_value", 0)))


# ==========================================================================
# Saved bets
# ==========================================================================

class SavedBetsPanel(tk.Frame):
    def __init__(self, master, store: BetStore, on_load, on_status):
        super().__init__(master, bg=T.BG)
        self.store = store
        self._on_load = on_load
        self._on_status = on_status
        self._selected = None
        self._rows = {}

        card = W.Card(self, bg=T.CARD, outline=T.BORDER_SOFT, padding=20,
                      parent_bg=T.BG)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="Load a saved bet", bg=T.CARD, fg=T.TEXT,
                 font=T.FONT_H2).pack(side="left")
        self.count_pill = W.Pill(head, "0", fg=T.ACCENT, bg=T.ACCENT_DIM)
        self.count_pill.pack(side="right")

        tk.Label(body, text="Double-click a bet to rename it", bg=T.CARD,
                 fg=T.FAINT, font=T.FONT_SM, anchor="w").pack(fill="x",
                                                              pady=(3, 12))

        # The list and the empty message swap places inside their own
        # container. pack_forget() + pack() sends a widget to the end of its
        # parent's packing order, so swapping them directly in the card body
        # would drop the list below the action buttons.
        self.content = tk.Frame(body, bg=T.CARD)
        self.content.pack(fill="both", expand=True)

        self.list = W.ScrollFrame(self.content, bg=T.CARD, height=1)
        self.list.pack(fill="both", expand=True)

        self.empty = tk.Label(self.content, text="", bg=T.CARD, fg=T.FAINT,
                              font=T.FONT_SM, justify="center", wraplength=280)

        W.divider(body, pady=14)

        actions = tk.Frame(body, bg=T.CARD)
        actions.pack(fill="x")
        self.btn_load = W.Button(actions, "Load", command=self._load,
                                 kind="primary", height=30)
        self.btn_load.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_rename = W.Button(actions, "Rename", command=self._rename,
                                   kind="ghost", height=30)
        self.btn_rename.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.btn_delete = W.Button(actions, "Delete", command=self._delete,
                                   kind="danger", height=30)
        self.btn_delete.pack(side="left", expand=True, fill="x")

        self.refresh()

    # -- rendering --------------------------------------------------------

    def refresh(self, select=None):
        for child in self.list.inner.winfo_children():
            child.destroy()
        self._rows.clear()

        # Only calculated bets can be reopened in a calculator; the full
        # ledger, hand-entered bets included, lives on the Bet Log tab.
        bets = [b for b in self.store.all()
                if b.get("kind") in (ARBITRAGE, EV)]
        self.count_pill.set_text(str(len(bets)))

        if not bets:
            self.list.pack_forget()
            self.empty.configure(
                text="Nothing saved yet.\nRun a calculation and hit "
                     "“Save this bet”.")
            self.empty.pack(fill="both", expand=True, pady=30)
            self._selected = None
            self._sync_buttons()
            return

        self.empty.pack_forget()
        self.list.pack(fill="both", expand=True)

        for bet in bets:
            self._rows[bet["id"]] = self._build_row(bet)

        if select and select in self._rows:
            self._select(select)
        elif self._selected in self._rows:
            self._select(self._selected)
        else:
            self._selected = None
        self._sync_buttons()

    def _build_row(self, bet):
        is_arb = bet.get("kind") == ARBITRAGE
        row = tk.Frame(self.list.inner, bg=T.CARD_ALT, cursor="hand2")
        row.pack(fill="x", pady=(0, 6))

        strip = tk.Frame(row, bg=T.ACCENT if is_arb else T.GREEN, width=3)
        strip.pack(side="left", fill="y")

        inner = tk.Frame(row, bg=T.CARD_ALT, padx=11, pady=9)
        inner.pack(side="left", fill="both", expand=True)

        top = tk.Frame(inner, bg=T.CARD_ALT)
        top.pack(fill="x")
        name = tk.Label(top, text=bet["name"], bg=T.CARD_ALT, fg=T.TEXT,
                        font=T.FONT_BOLD, anchor="w")
        name.pack(side="left")
        badge = tk.Label(top, text="ARB" if is_arb else "EV", bg=T.CARD_ALT,
                         fg=T.ACCENT if is_arb else T.GREEN, font=T.FONT_XS)
        badge.pack(side="right")

        summariser = ArbitragePanel.summary if is_arb else EVPanel.summary
        sub = tk.Label(inner, text=summariser(bet), bg=T.CARD_ALT, fg=T.MUTED,
                       font=T.FONT_SM, anchor="w", justify="left")
        sub.pack(fill="x", pady=(2, 0))

        stamp = tk.Label(inner, text=bet.get("created", "")[:16].replace("T", "  "),
                         bg=T.CARD_ALT, fg=T.FAINT, font=T.FONT_XS, anchor="w")
        stamp.pack(fill="x", pady=(3, 0))

        for widget in (row, inner, top, name, badge, sub, stamp):
            widget.bind("<Button-1>", lambda e, i=bet["id"]: self._select(i))
            widget.bind("<Double-Button-1>", lambda e, i=bet["id"]:
                        (self._select(i), self._rename()))

        return {"frame": row, "strip": strip,
                "surfaces": [row, inner, top, name, badge, sub, stamp]}

    def _select(self, bet_id):
        self._selected = bet_id
        for bid, parts in self._rows.items():
            active = bid == bet_id
            bg = T.FIELD_HOVER if active else T.CARD_ALT
            for surface in parts["surfaces"]:
                try:
                    surface.configure(bg=bg)
                except tk.TclError:
                    pass
            parts["frame"].configure(
                highlightthickness=1, highlightbackground=T.ACCENT if active
                else T.CARD_ALT)
        self._sync_buttons()

    def _sync_buttons(self):
        enabled = self._selected is not None
        for btn in (self.btn_load, self.btn_rename, self.btn_delete):
            btn.set_enabled(enabled)

    # -- actions ----------------------------------------------------------

    def _load(self):
        bet = self.store.get(self._selected) if self._selected else None
        if bet:
            self._on_load(bet)

    def _rename(self):
        bet = self.store.get(self._selected) if self._selected else None
        if not bet:
            return
        prompt = TextPrompt(self.winfo_toplevel(), "Rename bet",
                            "Give this bet a name you will recognise later.",
                            initial=bet["name"], ok_text="Rename")
        if prompt.result:
            self.store.rename(bet["id"], prompt.result)
            self.refresh(select=bet["id"])
            self._on_status("Renamed to “{}”".format(prompt.result))

    def _delete(self):
        bet = self.store.get(self._selected) if self._selected else None
        if not bet:
            return
        confirm = ConfirmPrompt(self.winfo_toplevel(), "Delete bet",
                                "Delete “{}”? This cannot be undone."
                                .format(bet["name"]))
        if confirm.result:
            self.store.delete(bet["id"])
            self._selected = None
            self.refresh()
            self._on_status("Deleted “{}”".format(bet["name"]))


# ==========================================================================
# Application
# ==========================================================================

# ==========================================================================
# Bet log
# ==========================================================================

class ManualBetDialog(tk.Toplevel):
    """Record any bet by hand, into the same schema the calculators use."""

    def __init__(self, parent, initial=None):
        super().__init__(parent, bg=T.BG)
        self.result = None
        initial = initial or {}
        editing = bool(initial)
        self.title("Edit bet" if editing else "Record a bet")
        self.transient(parent)
        self.resizable(False, False)

        card = W.Card(self, bg=T.CARD, outline=T.BORDER, padding=24,
                      parent_bg=T.BG)
        card.pack(fill="both", expand=True, padx=14, pady=14)
        body = card.body

        tk.Label(body, text="Edit bet" if editing else "Record a bet",
                 bg=T.CARD, fg=T.TEXT, font=T.FONT_H2, anchor="w").pack(fill="x")
        tk.Label(body,
                 text="Any bet at all — a single, an each-way, a bet a mate "
                      "offered you. Only the selection is required; leave the "
                      "rest blank if it does not apply.",
                 bg=T.CARD, fg=T.MUTED, font=T.FONT_SM, anchor="w",
                 justify="left", wraplength=520).pack(fill="x", pady=(4, 16))

        self.vars = {
            "name": tk.StringVar(
                value=initial.get("selection") or initial.get("name", "")),
            "event": tk.StringVar(value=initial.get("event", "")),
            "bookmaker": tk.StringVar(value=initial.get("bookmaker", "")),
            "odds": tk.StringVar(value=initial.get("odds", "")),
            "stake": tk.StringVar(value=initial.get("stake", "")),
            "payout": tk.StringVar(value=initial.get("payout", "")),
            "date": tk.StringVar(value=initial.get("date", _date.today().isoformat())),
            "notes": tk.StringVar(value=initial.get("notes", "")),
        }
        self.odds_format = initial.get("odds_format", core.DECIMAL)
        self.status = initial.get("status", DEFAULT_STATUS)
        self.choices = {}

        grid = tk.Frame(body, bg=T.CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, minsize=250, weight=1)
        grid.grid_columnconfigure(3, minsize=190, weight=1)

        def field(row, column, label, key, **kw):
            tk.Label(grid, text=label, bg=T.CARD, fg=T.TEXT_DIM,
                     font=T.FONT_SM, anchor="w").grid(
                         row=row, column=column, sticky="w",
                         padx=(0, 12), pady=6)
            holder = tk.Frame(grid, bg=T.BORDER, padx=1, pady=1)
            holder.grid(row=row, column=column + 1, sticky="ew",
                        padx=(0, 20 if column == 0 else 0), pady=6)
            entry = tk.Entry(holder, textvariable=self.vars[key], bg=T.FIELD,
                             fg=T.TEXT, font=T.FONT, relief="flat", bd=0,
                             insertbackground=T.ACCENT, highlightthickness=0,
                             selectbackground=T.ACCENT_DIM, **kw)
            entry.pack(fill="x", ipady=5, padx=8)
            entry.bind("<FocusIn>", lambda e, h=holder: h.configure(bg=T.ACCENT))
            entry.bind("<FocusOut>", lambda e, h=holder: h.configure(bg=T.BORDER))
            return entry

        def choice(row, column, label, key, options, initial_value):
            tk.Label(grid, text=label, bg=T.CARD, fg=T.TEXT_DIM,
                     font=T.FONT_SM, anchor="w").grid(
                         row=row, column=column, sticky="w",
                         padx=(0, 12), pady=6)
            control = W.Dropdown(grid, [(o, o or "—") for o in options],
                                 bg=T.CARD, min_width=250)
            control.set(initial_value)
            control.grid(row=row, column=column + 1, sticky="ew",
                         padx=(0, 20 if column == 0 else 0), pady=6)
            self.choices[key] = control
            return control

        self.name_entry = field(0, 0, "Selection *", "name")
        field(0, 2, "Date", "date")
        field(1, 0, "Event", "event")
        field(1, 2, "Bookmaker", "bookmaker")
        choice(2, 0, "Sport", "sport", betlog.SPORTS,
               initial.get("sport", ""))
        choice(2, 2, "Type", "bet_type", betlog.BET_TYPES,
               initial.get("bet_type",
                           "" if editing else betlog.DEFAULT_BET_TYPE))
        field(3, 0, "Odds", "odds")
        field(3, 2, "Stake", "stake")
        field(4, 0, "Payout", "payout")
        field(4, 2, "Notes", "notes")

        # Odds format + payout helper sit under the numeric fields.
        tools = tk.Frame(body, bg=T.CARD)
        tools.pack(fill="x", pady=(14, 0))
        tk.Label(tools, text="Odds format", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT_SM).pack(side="left", padx=(0, 8))
        self.format_control = W.SegmentedControl(
            tools, [(core.DECIMAL, "Decimal"), (core.AMERICAN, "American"),
                    (core.FRACTIONAL, "Fractional")],
            command=self._set_format, bg=T.CARD, font=T.FONT_SM,
            padx=10, pady=3)
        self.format_control.pack(side="left")
        self.format_control.set(self.odds_format)
        W.Button(tools, "Fill payout", command=self._fill_payout, kind="ghost",
                 width=104, height=27, font=T.FONT_SM).pack(side="left",
                                                            padx=(14, 0))

        status_row = tk.Frame(body, bg=T.CARD)
        status_row.pack(fill="x", pady=(12, 0))
        tk.Label(status_row, text="Status", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT_SM).pack(side="left", padx=(0, 8))
        self.status_control = W.SegmentedControl(
            status_row, [(s, s) for s in STATUSES],
            command=self._set_status, bg=T.CARD, font=T.FONT_SM,
            padx=10, pady=3)
        self.status_control.pack(side="left")
        self.status_control.set(self.status)

        self.error = tk.Label(body, text="", bg=T.CARD, fg=T.AMBER,
                              font=T.FONT_SM, anchor="w")
        self.error.pack(fill="x", pady=(12, 0))

        row = tk.Frame(body, bg=T.CARD)
        row.pack(fill="x", pady=(6, 0))
        W.Button(row, "Cancel", command=self._cancel, kind="ghost",
                 width=92).pack(side="right", padx=(8, 0))
        W.Button(row, "Save changes" if editing else "Record bet",
                 command=self._ok, kind="primary", width=136).pack(side="right")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 4
        self.geometry("+{}+{}".format(max(x, 0), max(y, 0)))
        self.name_entry.focus_set()
        self.grab_set()
        self.wait_window(self)

    def _set_format(self, fmt):
        self.odds_format = fmt

    def _set_status(self, status):
        self.status = status

    def _fill_payout(self):
        payout = betlog.suggested_payout(self.vars["odds"].get(),
                                         self.vars["stake"].get(),
                                         self.odds_format)
        if payout is None:
            self.error.configure(text="Enter valid odds and a stake first.")
            return
        self.error.configure(text="")
        self.vars["payout"].set("{:.2f}".format(payout))

    def _ok(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        if not values["name"]:
            self.error.configure(text="Give the bet a selection.")
            self.name_entry.focus_set()
            return
        for key in ("stake", "payout"):
            if values[key] and betlog._number(values[key]) is None:
                self.error.configure(
                    text="{} must be a number, or left blank.".format(key.title()))
                return
        # The log filters by date, so it has to be a date it can read.
        if values["date"] and betlog.parse_date(values["date"]) is None:
            self.error.configure(text="Date must be YYYY-MM-DD, like "
                                      + _date.today().isoformat() + ".")
            return
        values.update({k: c.get() for k, c in self.choices.items()})
        values["odds_format"] = self.odds_format
        values["status"] = self.status
        self.result = values
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class BetLogPanel(tk.Frame):
    """Every bet in one table, with manual entry and CSV export."""

    kind = LOG

    COLUMN_WEIGHTS = {
        "Date": (0, 80), "Sport": (0, 96), "Selection": (4, 200),
        "Bet Type": (0, 82), "Odds": (0, 96), "Stake": (0, 88),
        "Payout": (0, 92), "P/L": (0, 100), "Status": (0, 76),
    }
    RIGHT_ALIGNED = ("Stake", "Payout", "P/L")
    MARKER_WIDTH = 3

    def __init__(self, master, store, on_status, on_load):
        super().__init__(master, bg=T.BG)
        self.store = store
        self._on_status = on_status
        self._on_load = on_load
        self._selected = None
        self._rows = {}
        self._markers = {}
        self._filter = "all"
        self._period = "all"
        self._build()
        self.refresh()

    # -- layout -----------------------------------------------------------

    def _build(self):
        card = W.Card(self, bg=T.CARD, outline=T.BORDER_SOFT, padding=22,
                      parent_bg=T.BG)
        card.pack(fill="both", expand=True)
        body = card.body

        head = tk.Frame(body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="Bet Log", bg=T.CARD, fg=T.TEXT,
                 font=T.FONT_H2).pack(side="left")
        self.count_pill = W.Pill(head, "0", fg=T.ACCENT, bg=T.ACCENT_DIM)
        self.count_pill.pack(side="left", padx=(10, 0))

        W.Button(head, "Export CSV", command=self.export_csv, kind="ghost",
                 width=112).pack(side="right")
        W.Button(head, "Record a bet", command=self.record_bet, kind="primary",
                 width=132).pack(side="right", padx=(0, 10))

        self.summary = tk.Label(body, text="", bg=T.CARD, fg=T.MUTED,
                                font=T.FONT_SM, anchor="w")
        self.summary.pack(fill="x", pady=(6, 14))

        filters = tk.Frame(body, bg=T.CARD)
        filters.pack(fill="x", pady=(0, 12))
        self.filter_control = W.SegmentedControl(
            filters,
            [("all", "All"), (ARBITRAGE, "Arbitrage"), (EV, "Expected Value"),
             (MANUAL, "Manual")],
            command=self._set_filter, bg=T.CARD, font=T.FONT_SM,
            padx=12, pady=4)
        self.filter_control.pack(side="left")

        tk.Label(filters, text="Period", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT_SM).pack(side="left", padx=(20, 8))
        self.period_control = W.Dropdown(filters, betlog.PERIODS,
                                         command=self._set_period, bg=T.CARD)
        self.period_control.pack(side="left")

        header = tk.Frame(body, bg=T.CARD)
        header.pack(fill="x")
        header.grid_columnconfigure(0, weight=0, minsize=self.MARKER_WIDTH)
        for index, column in enumerate(betlog.TABLE_COLUMNS, start=1):
            weight, minsize = self.COLUMN_WEIGHTS[column]
            header.grid_columnconfigure(index, weight=weight, minsize=minsize)
            tk.Label(header, text=column, bg=T.CARD, fg=T.FAINT,
                     font=T.FONT_XS, padx=6,
                     anchor="e" if column in self.RIGHT_ALIGNED else "w").grid(
                         row=0, column=index, sticky="ew", pady=(0, 6))
        tk.Frame(body, bg=T.BORDER_SOFT, height=1).pack(fill="x")

        # See SavedBetsPanel: the table and the empty message swap inside
        # their own container so neither can end up below the actions row.
        self.content = tk.Frame(body, bg=T.CARD)
        self.content.pack(fill="both", expand=True, pady=(2, 0))

        self.table = W.ScrollFrame(self.content, bg=T.CARD, height=1)
        self.table.pack(fill="both", expand=True)
        self.grid_host = tk.Frame(self.table.inner, bg=T.CARD)
        self.grid_host.pack(fill="both", expand=True)
        self.grid_host.grid_columnconfigure(0, weight=0,
                                            minsize=self.MARKER_WIDTH)
        for index, column in enumerate(betlog.TABLE_COLUMNS, start=1):
            weight, minsize = self.COLUMN_WEIGHTS[column]
            self.grid_host.grid_columnconfigure(index, weight=weight,
                                                minsize=minsize)

        self.empty = tk.Label(self.content, text="", bg=T.CARD, fg=T.FAINT,
                              font=T.FONT_SM, justify="center")

        W.divider(body, pady=14)

        actions = tk.Frame(body, bg=T.CARD)
        actions.pack(fill="x")
        tk.Label(actions, text="Mark selected", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT_SM).pack(side="left", padx=(0, 8))
        self.status_control = W.SegmentedControl(
            actions, [(s, s) for s in STATUSES], command=self._set_status,
            bg=T.CARD, font=T.FONT_SM, padx=11, pady=4)
        self.status_control.pack(side="left")

        self.btn_delete = W.Button(actions, "Delete", command=self._delete,
                                   kind="danger", width=92)
        self.btn_delete.pack(side="right")
        self.btn_rename = W.Button(actions, "Rename", command=self._rename,
                                   kind="ghost", width=92)
        self.btn_rename.pack(side="right", padx=(0, 8))
        self.btn_edit = W.Button(actions, "Edit", command=self._edit,
                                 kind="ghost", width=92)
        self.btn_edit.pack(side="right", padx=(0, 8))
        self.btn_open = W.Button(actions, "Open in calculator",
                                 command=self._open, kind="ghost", width=152)
        self.btn_open.pack(side="right", padx=(0, 8))

    # -- data -------------------------------------------------------------

    @staticmethod
    def _signed(value, money=True):
        text = core.money(value) if money else core.pct(abs(value), 1)
        return ("+" if value >= 0 else ("" if money else "-")) + text

    def _visible_bets(self):
        bets = self.store.all()
        if self._filter != "all":
            bets = [b for b in bets if b.get("kind") == self._filter]
        if self._period != "all":
            bets = [b for b in bets
                    if betlog.in_period(betlog.log_row(b)["Date"], self._period)]
        return bets

    def _set_filter(self, key):
        self._filter = key
        self.refresh()

    def _set_period(self, key):
        self._period = key
        self.refresh()

    def refresh(self, select=None):
        for child in self.grid_host.winfo_children():
            child.destroy()
        self._rows.clear()
        self._markers.clear()

        bets = self._visible_bets()
        self.count_pill.set_text(str(len(bets)))

        figures = betlog.totals(bets)
        parts = ["{} bet{}".format(figures["count"],
                                   "" if figures["count"] == 1 else "s"),
                 "{} staked".format(core.money(figures["staked"]))]
        if figures["open_count"]:
            parts.append("{} open, projected {}".format(
                figures["open_count"], self._signed(figures["projected"])))
        if figures["settled_count"]:
            parts.append("settled {} ({} ROI)".format(
                self._signed(figures["settled"]),
                self._signed(figures["roi_pct"], money=False)))
        self.summary.configure(text="  ·  ".join(parts))

        if not bets:
            self.table.pack_forget()
            self.empty.configure(
                text="Nothing logged yet.\nSave a calculation, or hit "
                     "“Record a bet” to enter one by hand.")
            self.empty.pack(fill="both", expand=True, pady=40)
            self._selected = None
            self._sync_buttons()
            return

        self.empty.pack_forget()
        self.table.pack(fill="both", expand=True)

        for index, bet in enumerate(bets):
            self._rows[bet["id"]] = self._build_row(index, bet)

        if select and select in self._rows:
            self._select(select)
        elif self._selected in self._rows:
            self._select(self._selected)
        else:
            self._selected = None
        self._sync_buttons()

    def _build_row(self, index, bet):
        row = betlog.log_row(bet)
        marker = tk.Frame(self.grid_host, bg=T.CARD, width=self.MARKER_WIDTH)
        marker.grid(row=index, column=0, sticky="nsew")
        self._markers[bet["id"]] = marker

        cells = []
        for column_index, column in enumerate(betlog.TABLE_COLUMNS, start=1):
            value = row[column]
            if column in betlog.NUMERIC_COLUMNS:
                text = core.money(value) if value is not None else "—"
                if column == "P/L" and value:
                    text = ("+" if value > 0 else "") + text
            else:
                text = str(value or "—")

            fg = T.TEXT_DIM
            if column == "Selection":
                fg = T.TEXT
            elif column == "P/L" and value:
                fg = T.GREEN if value > 0 else T.RED
            elif column == "Status":
                fg = {"Won": T.GREEN, "Lost": T.RED,
                      "Void": T.FAINT}.get(text, T.MUTED)
            elif column in ("Sport", "Bet Type"):
                fg = T.MUTED

            label = tk.Label(
                self.grid_host, text=text, bg=T.CARD, fg=fg,
                font=T.FONT_BOLD if column == "Selection" else T.FONT_SM,
                padx=6, pady=5,
                anchor="e" if column in self.RIGHT_ALIGNED else "w")
            # No external padding: gaps between cells would break the row
            # highlight into separate blocks.
            label.grid(row=index, column=column_index, sticky="nsew")
            label.bind("<Button-1>", lambda e, i=bet["id"]: self._select(i))
            label.bind("<Double-Button-1>",
                       lambda e, i=bet["id"]: (self._select(i), self._edit()))
            label.bind("<Enter>", lambda e, i=bet["id"]: self._hover(i, True))
            label.bind("<Leave>", lambda e, i=bet["id"]: self._hover(i, False))
            cells.append(label)
        return cells

    def _paint(self, bet_id, background, marker_colour):
        for cell in self._rows.get(bet_id, ()):
            cell.configure(bg=background)
        marker = self._markers.get(bet_id)
        if marker is not None:
            marker.configure(bg=marker_colour)

    def _hover(self, bet_id, entering):
        if bet_id == self._selected:
            return          # the selection outranks the pointer
        self._paint(bet_id, T.ROW_HOVER if entering else T.CARD, T.CARD)

    def _select(self, bet_id):
        self._selected = bet_id
        for other_id in self._rows:
            chosen = other_id == bet_id
            self._paint(other_id,
                        T.ROW_SELECTED if chosen else T.CARD,
                        T.ACCENT if chosen else T.CARD)
        self._sync_buttons()

    def _sync_buttons(self):
        bet = self.store.get(self._selected) if self._selected else None
        self.btn_rename.set_enabled(bet is not None)
        self.btn_delete.set_enabled(bet is not None)
        self.btn_edit.set_enabled(bet is not None and bet.get("kind") == MANUAL)
        self.btn_open.set_enabled(bet is not None
                                  and bet.get("kind") in (ARBITRAGE, EV))
        if bet is not None:
            self.status_control.set(bet.get("status", DEFAULT_STATUS))

    # -- actions ----------------------------------------------------------

    def record_bet(self):
        dialog = ManualBetDialog(self.winfo_toplevel())
        if not dialog.result:
            return
        values = dialog.result
        status = values.pop("status", DEFAULT_STATUS)
        bet = self.store.add(
            values.pop("name"), MANUAL, values,
            betlog.manual_results(values.get("stake"), values.get("payout")),
            status=status)
        self._filter = "all"
        self.filter_control.set("all")
        self.refresh(select=bet["id"])
        self._on_status("Recorded “{}”".format(bet["name"]))

    def _edit(self):
        bet = self.store.get(self._selected) if self._selected else None
        if bet is None or bet.get("kind") != MANUAL:
            return
        initial = dict(bet.get("inputs") or {})
        initial["name"] = bet["name"]
        initial["status"] = bet.get("status", DEFAULT_STATUS)
        dialog = ManualBetDialog(self.winfo_toplevel(), initial=initial)
        if not dialog.result:
            return
        values = dialog.result
        name = values.pop("name")
        status = values.pop("status", DEFAULT_STATUS)
        self.store.update(bet["id"], values,
                          betlog.manual_results(values.get("stake"),
                                                values.get("payout")),
                          name=name)
        self.store.set_status(bet["id"], status)
        self.refresh(select=bet["id"])
        self._on_status("Updated “{}”".format(name))

    def _set_status(self, status):
        bet = self.store.get(self._selected) if self._selected else None
        if bet is None or bet.get("status") == status:
            return
        self.store.set_status(bet["id"], status)
        self.refresh(select=bet["id"])
        self._on_status("“{}” marked {}".format(bet["name"], status))

    def _rename(self):
        bet = self.store.get(self._selected) if self._selected else None
        if bet is None:
            return
        prompt = TextPrompt(self.winfo_toplevel(), "Rename bet",
                            "Give this bet a name you will recognise later.",
                            initial=bet["name"], ok_text="Rename")
        if prompt.result:
            self.store.rename(bet["id"], prompt.result)
            self.refresh(select=bet["id"])
            self._on_status("Renamed to “{}”".format(prompt.result))

    def _delete(self):
        bet = self.store.get(self._selected) if self._selected else None
        if bet is None:
            return
        confirm = ConfirmPrompt(self.winfo_toplevel(), "Delete bet",
                                "Delete “{}”? This cannot be undone."
                                .format(bet["name"]))
        if confirm.result:
            self.store.delete(bet["id"])
            self._selected = None
            self.refresh()
            self._on_status("Deleted “{}”".format(bet["name"]))

    def _open(self):
        bet = self.store.get(self._selected) if self._selected else None
        if bet and bet.get("kind") in (ARBITRAGE, EV):
            self._on_load(bet)

    def export_csv(self):
        bets = self._visible_bets()
        if not bets:
            self._on_status("Nothing to export.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export bet log",
            defaultextension=".csv",
            initialfile=betlog.default_filename(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            written = betlog.export_csv(bets, path)
        except OSError as exc:
            self._on_status("Export failed: {}".format(exc))
            return
        scope = "" if self._filter == "all" else " ({} only)".format(
            betlog.TYPE_LABELS.get(self._filter, self._filter))
        self._on_status("Exported {} bet{}{} to {}".format(
            written, "" if written == 1 else "s", scope,
            os.path.basename(path)))


# ==========================================================================
# Application
# ==========================================================================

class App(tk.Tk):
    def __init__(self, store_path=None):
        super().__init__()
        self.title("{} {}".format(APP_TITLE, __version__))
        self.configure(bg=T.BG)
        self.geometry("1240x910")
        self.minsize(1080, 720)
        T.resolve_fonts(self)

        self.store = BetStore(store_path) if store_path else BetStore()

        self._build_header()
        self._build_body()
        self._build_statusbar()

        self.bind("<Escape>", lambda e: self.focus_set())
        self.bind("<Control-s>", lambda e: self._save_current())

    # -- chrome -----------------------------------------------------------

    def _build_header(self):
        header = tk.Frame(self, bg=T.BG)
        header.pack(fill="x", padx=26, pady=(20, 14))

        left = tk.Frame(header, bg=T.BG)
        left.pack(side="left")
        mark = tk.Frame(left, bg=T.ACCENT, width=4, height=30)
        mark.pack(side="left", padx=(0, 12))
        titles = tk.Frame(left, bg=T.BG)
        titles.pack(side="left")
        title_row = tk.Frame(titles, bg=T.BG)
        title_row.pack(fill="x")
        tk.Label(title_row, text=APP_TITLE, bg=T.BG, fg=T.TEXT,
                 font=T.FONT_H1, anchor="w").pack(side="left")
        W.Pill(title_row, "BETA", fg=T.AMBER,
               bg="#3a2c14").pack(side="left", padx=(10, 0), pady=(6, 0))
        tk.Label(titles, text="Arbitrage, expected value, and every bet logged",
                 bg=T.BG, fg=T.MUTED, font=T.FONT_SM, anchor="w").pack(fill="x")

        tabs_holder = tk.Frame(header, bg=T.CARD, padx=3, pady=3)
        tabs_holder.pack(side="right")
        self.tabs = W.SegmentedControl(
            tabs_holder,
            [(ARBITRAGE, "  Arbitrage  "), (EV, "  Expected Value  "),
             (LOG, "  Bet Log  ")],
            command=self._switch_tab, bg=T.CARD,
        )
        self.tabs.pack()

    def _build_body(self):
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=26)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=340, weight=0)
        body.grid_rowconfigure(0, weight=1)

        stack = tk.Frame(body, bg=T.BG)
        stack.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        stack.grid_rowconfigure(0, weight=1)
        stack.grid_columnconfigure(0, weight=1)

        self.calculators = {
            ARBITRAGE: ArbitragePanel(stack, self._save_bet, self.set_status),
            EV: EVPanel(stack, self._save_bet, self.set_status),
        }
        # give each calculator a handle on its own format control for restore()
        for panel in self.calculators.values():
            panel.format_control = self._find_format_control(panel)

        self.log = BetLogPanel(stack, self.store, self.set_status,
                               self._load_bet)

        self.panels = dict(self.calculators)
        self.panels[LOG] = self.log
        for panel in self.panels.values():
            panel.grid(row=0, column=0, sticky="nsew")

        self._stack = stack
        self._body = body
        self.saved = SavedBetsPanel(body, self.store, self._load_bet,
                                    self.set_status)
        self.saved.grid(row=0, column=1, sticky="nsew")

        self._switch_tab(ARBITRAGE)

    @staticmethod
    def _find_format_control(panel):
        stack = [panel]
        while stack:
            widget = stack.pop()
            if isinstance(widget, W.SegmentedControl):
                return widget
            stack.extend(widget.winfo_children())
        return None

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=26, pady=(10, 14))
        self.status = tk.Label(bar, text="Ready", bg=T.BG, fg=T.FAINT,
                               font=T.FONT_SM, anchor="w")
        self.status.pack(side="left")
        tk.Label(bar, text=self._short_path(self.store.path), bg=T.BG,
                 fg="#2f3b48", font=T.FONT_XS, anchor="e").pack(side="right")

    @staticmethod
    def _short_path(path):
        """Collapse the home directory, so the bar shows a "~" prefix rather
        than spelling out the user's home folder."""
        home = os.path.expanduser("~")
        if path.lower().startswith(home.lower()):
            return "~" + path[len(home):]
        return path

    # -- behaviour --------------------------------------------------------

    def set_status(self, message):
        self.status.configure(text=message)
        self.after(6000, lambda: self.status.configure(text="Ready")
                   if self.status.cget("text") == message else None)

    def _switch_tab(self, key):
        self.panels[key].tkraise()
        # The log is a full-width table; the quick-load list beside it would
        # only duplicate it, so it steps aside.
        if key == LOG:
            self.saved.grid_remove()
            # grid_remove hides the panel but the column keeps its minsize,
            # so release that too or the table stops 340px short.
            self._body.grid_columnconfigure(1, minsize=0)
            self._stack.grid_configure(padx=0)
            self.log.refresh()
        else:
            self.saved.grid()
            self._body.grid_columnconfigure(1, minsize=340)
            self._stack.grid_configure(padx=(0, 18))

    def _current_panel(self):
        return self.panels[self.tabs.get()]

    def _save_current(self):
        panel = self._current_panel()
        if panel is self.log:
            self.log.record_bet()
        else:
            self._save_bet(panel)

    def _save_bet(self, panel):
        if panel.result is None:
            self.set_status("Fix the inputs before saving.")
            return
        prompt = TextPrompt(self, "Save bet",
                            "Name this bet so you can find it again. You can "
                            "rename it any time from the saved list.",
                            initial=panel.default_name(), ok_text="Save bet")
        if not prompt.result:
            return
        inputs, results = panel.snapshot()
        bet = self.store.add(prompt.result, panel.kind, inputs, results)
        self.saved.refresh(select=bet["id"])
        self.log.refresh()
        self.set_status("Saved “{}”".format(bet["name"]))

    def _load_bet(self, bet):
        kind = bet.get("kind", ARBITRAGE)
        panel = self.calculators.get(kind)
        if panel is None:
            self.set_status("Only calculated bets open in a calculator.")
            return
        self.tabs.set(kind)
        self._switch_tab(kind)
        panel.restore(bet.get("inputs", {}))
        self.set_status("Loaded “{}”".format(bet["name"]))


def main():
    App().mainloop()
