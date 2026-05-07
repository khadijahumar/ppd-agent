"""FT (Finish Temperature) and CT (Coil Temperature) standard code tables.

Source: user-supplied reference (image attached during conversation, May 2025).
Each code maps to a target temperature (°C) and a tolerance VAR (± °C).

These tables supersede whatever historical mapping was in ``FT_CT_Design.xlsx``
— for any new analysis the agent should resolve codes via this module.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TempCode:
    """One temperature code: a target value with ± tolerance."""
    code: str
    target: float
    var: float

    @property
    def low(self) -> float:
        return self.target - self.var

    @property
    def high(self) -> float:
        return self.target + self.var


# ---------------------------------------------------------------------------
# Finish Temperature (FT) codes
# ---------------------------------------------------------------------------
FT_CODES: dict[str, TempCode] = {
    code: TempCode(code, target, var) for code, target, var in [
        ("A", 780, 15),
        ("B", 790, 15),
        ("C", 800, 15),
        ("D", 820, 15),
        ("E", 840, 15),
        ("F", 850, 20),
        ("G", 860, 15),
        ("H", 870, 15),
        ("I", 880, 20),
        ("K", 890, 15),
        ("L", 900, 15),
        ("M", 910, 15),
        ("N", 810, 15),
        ("P", 800, 30),
        ("Q", 830, 15),
        ("R", 840, 30),
        ("S", 850, 30),
        ("T", 860, 30),
        ("U", 870, 30),
        ("V", 880, 30),
        ("W", 890, 30),
        ("X", 900, 30),
        ("Y", 920, 30),
        ("Z", 940, 20),
    ]
}


# ---------------------------------------------------------------------------
# Coil Temperature (CT) codes
# ---------------------------------------------------------------------------
CT_CODES: dict[str, TempCode] = {
    code: TempCode(code, target, var) for code, target, var in [
        ("A", 560, 20),
        ("B", 570, 15),
        ("C", 580, 20),
        ("D", 590, 15),
        ("E", 600, 20),
        ("F", 610, 15),
        ("G", 620, 15),
        ("H", 630, 15),
        ("I", 640, 15),
        ("K", 650, 20),
        ("L", 660, 15),
        ("M", 670, 15),
        ("N", 680, 15),
        ("O", 520, 15),
        ("P", 700, 15),
        ("Q", 720, 15),
        ("R", 540, 15),
        ("S", 580, 30),
        ("T", 570, 30),
        ("U", 590, 30),
        ("V", 640, 30),
        ("W", 680, 30),
        ("X", 710, 30),
        ("Y", 740, 30),
        ("Z", 770, 30),
    ]
}


def resolve_ft(code: str) -> TempCode | None:
    """Resolve a Finish Temperature code (case-insensitive)."""
    if not code:
        return None
    return FT_CODES.get(code.strip().upper())


def resolve_ct(code: str) -> TempCode | None:
    """Resolve a Coil Temperature code (case-insensitive)."""
    if not code:
        return None
    return CT_CODES.get(code.strip().upper())


def list_ft_codes() -> list[TempCode]:
    return list(FT_CODES.values())


def list_ct_codes() -> list[TempCode]:
    return list(CT_CODES.values())
