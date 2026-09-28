"""Parsing/formatting of the position files (buildings.txt, unitstacks.txt, weatherpositions.txt)."""
from __future__ import annotations

import numpy as np

from .mapdata import game_to_pixel

PER_LAND = ("bunker", "supply_node", "special_project_facility_spawn")
PER_COAST = ("naval_base_spawn", "coastal_bunker", "naval_supply_hub", "naval_headquarters", "floating_harbor")
PER_PROVINCE = PER_LAND + PER_COAST


def split_lines(text: str):
    """(lines without newline, trailing newline?)"""
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines = lines[:-1]
    return lines, trailing


def join_lines(lines, trailing: bool) -> str:
    return "\n".join(lines) + ("\n" if trailing else "")


def position_pixels(lines, xcol: int, zcol: int, H: int, W: int, sep=";"):
    """Pixel (row, col) of every parsable line; None for others."""
    out = []
    for ln in lines:
        s = ln.split(sep)
        try:
            c, r = game_to_pixel(float(s[xcol]), float(s[zcol]), H)
        except (ValueError, IndexError):
            out.append(None)
            continue
        out.append((min(max(r, 0), H - 1), c % W))
    return out


def forbidden_mask(shape, texts_cols) -> np.ndarray:
    """bool mask of all pixels holding a position from the given (text, xcol, zcol) files."""
    H, W = shape
    m = np.zeros(shape, dtype=bool)
    for text, xc, zc in texts_cols:
        lines, _ = split_lines(text)
        for p in position_pixels(lines, xc, zc, H, W):
            if p is not None:
                m[p] = True
    return m
