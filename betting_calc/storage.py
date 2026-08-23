"""Persistence for saved bets.

Bets are stored as a JSON list in a single file next to the application.
Every record keeps both the inputs (so a bet can be reloaded into the
calculator) and the computed results (so the list can be browsed without
recomputing).
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime

ARBITRAGE = "arbitrage"
EV = "ev"
MANUAL = "manual"

#: Every bet carries one of these; calculated bets start Pending too, so the
#: exported log can be settled and totalled like any other ledger.
STATUSES = ("Pending", "Won", "Lost", "Void")
DEFAULT_STATUS = STATUSES[0]

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "saved_bets.json",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class BetStore:
    """A tiny JSON-backed collection of saved bets."""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._bets: list[dict] = []
        self.load()

    # -- io ---------------------------------------------------------------

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._bets = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._bets = data if isinstance(data, list) else list(data.get("bets", []))
            for bet in self._bets:
                bet.setdefault("status", DEFAULT_STATUS)
        except (OSError, ValueError):
            # A corrupt or unreadable file should not stop the app; keep the
            # bad file around under .bak so nothing is silently destroyed.
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            self._bets = []

    def save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._bets, fh, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # -- queries ----------------------------------------------------------

    def all(self) -> list[dict]:
        """Saved bets, newest first."""
        return sorted(self._bets, key=lambda b: b.get("created", ""), reverse=True)

    def get(self, bet_id: str) -> dict | None:
        for bet in self._bets:
            if bet.get("id") == bet_id:
                return bet
        return None

    def __len__(self) -> int:
        return len(self._bets)

    # -- mutations --------------------------------------------------------

    def add(self, name: str, kind: str, inputs: dict, results: dict,
            note: str = "", status: str = DEFAULT_STATUS) -> dict:
        bet = {
            "id": uuid.uuid4().hex,
            "name": name.strip() or "Untitled bet",
            "kind": kind,
            "note": note,
            "status": status if status in STATUSES else DEFAULT_STATUS,
            "created": _now(),
            "updated": _now(),
            "inputs": inputs,
            "results": results,
        }
        self._bets.append(bet)
        self.save()
        return bet

    def rename(self, bet_id: str, new_name: str) -> bool:
        bet = self.get(bet_id)
        if bet is None:
            return False
        bet["name"] = new_name.strip() or bet["name"]
        bet["updated"] = _now()
        self.save()
        return True

    def update(self, bet_id: str, inputs: dict, results: dict,
               name: str | None = None) -> bool:
        bet = self.get(bet_id)
        if bet is None:
            return False
        bet["inputs"] = inputs
        bet["results"] = results
        if name is not None:
            bet["name"] = name.strip() or bet["name"]
        bet["updated"] = _now()
        self.save()
        return True

    def set_status(self, bet_id: str, status: str) -> bool:
        """Mark a bet Pending / Won / Lost / Void."""
        bet = self.get(bet_id)
        if bet is None or status not in STATUSES:
            return False
        bet["status"] = status
        bet["updated"] = _now()
        self.save()
        return True

    def delete(self, bet_id: str) -> bool:
        before = len(self._bets)
        self._bets = [b for b in self._bets if b.get("id") != bet_id]
        if len(self._bets) == before:
            return False
        self.save()
        return True
