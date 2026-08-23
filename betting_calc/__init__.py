"""Bet Lab - arbitrage and expected value calculators."""

from .core import (  # noqa: F401
    EVResult,
    OddsError,
    TwoWayResult,
    american_to_decimal,
    compute_arbitrage,
    compute_ev,
    compute_two_way,
    decimal_to_american,
    hedge_stake,
    implied_probability,
)
from .storage import BetStore  # noqa: F401

__version__ = "0.1.0-beta"
