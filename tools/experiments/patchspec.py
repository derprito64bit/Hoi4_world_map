"""EXP-09 variant manifest (P00c contract, docs/logs/P00b.md section 1) and shader patch specs.

``apply_patch`` has exactly the semantics of the reference implementation in
P00c's ``tests/gfx/test_exp09.py``: entries are applied in list order; each
anchor must occur exactly once in the *current* text (after the previous
entries), otherwise the build fails; modes are before | after | replace. It is
the single shared implementation P00c's test can import later.

Only the keys of the contract are read; unknown keys (``experiment``,
``work_unit``, ``canvas``, ``install``, per-patch ``purpose``/``behaviour`` ...)
are ignored.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .common import KitError, decode, encode, is_within, safe_join

MANIFEST_REL = "assets/gfx/FX/experiments/EXP-09/variants.json"
MODES = ("before", "after", "replace")


@dataclass
class Variant:
    id: str
    label: str
    changes: str
    defines: list = field(default_factory=list)          # repo-relative .lua sources
    shader_patches: list = field(default_factory=list)   # repo-relative .patch.json sources


BASELINE_ONLY = Variant(
    id="a", label="EXP-09a baseline",
    changes="Baseline: only the off-globe filler (lake provinces, heightmap 89, ocean colormap tone); "
            "vanilla camera defines and shaders. Built without the P00c manifest.")


def apply_patch(text: str, spec: list) -> str:
    """Apply patch entries in order; every anchor must be unique in the current text."""
    for i, p in enumerate(spec):
        try:
            anchor, mode, new = p["anchor"], p["mode"], p["text"]
        except (KeyError, TypeError):
            raise KitError(f"patch {i}: needs 'anchor', 'mode' and 'text'") from None
        if not isinstance(anchor, str) or not anchor:
            raise KitError(f"patch {i}: empty anchor")
        if mode not in MODES:
            raise KitError(f"patch {i}: mode {mode!r} not in {MODES}")
        count = text.count(anchor)
        if count != 1:
            raise KitError(f"patch {i}: anchor {anchor!r} found {count} times")
        pos = text.index(anchor)
        end = pos + len(anchor)
        if mode == "before":
            text = text[:pos] + new + text[pos:]
        elif mode == "after":
            text = text[:end] + new + text[end:]
        else:
            text = text[:pos] + new + text[end:]
    return text


def load_manifest(repo_root: Path, rel: str = MANIFEST_REL):
    """List of Variant from the P00c manifest, or None if the manifest is absent."""
    path = Path(repo_root) / rel
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        raise KitError(f"{rel}: 'variants' must be a non-empty list")
    out, seen = [], set()
    for v in raw:
        vid = v.get("id")
        if not isinstance(vid, str) or not vid.isalnum() or not vid.islower() or vid in seen:
            raise KitError(f"{rel}: bad or duplicate variant id {vid!r}")
        seen.add(vid)
        defines, patches = v.get("defines", []), v.get("shader_patches", [])
        if not isinstance(defines, list) or not isinstance(patches, list):
            raise KitError(f"{rel}: variant {vid}: 'defines' and 'shader_patches' must be lists")
        for src in defines + patches:
            p = safe_join(repo_root, src)
            if not p.is_file():
                raise KitError(f"{rel}: variant {vid}: source {src} not found")
        for src in defines:
            if not src.endswith(".lua"):
                raise KitError(f"{rel}: variant {vid}: define source {src} is not a .lua file")
        out.append(Variant(id=vid, label=str(v.get("label", "")), changes=str(v.get("changes", "")),
                           defines=list(defines), shader_patches=list(patches)))
    if out[0].defines or out[0].shader_patches:
        raise KitError(f"{rel}: the first variant must be the baseline (no defines, no shader patches)")
    return out


def load_patch_spec(repo_root: Path, rel: str) -> list:
    spec = json.loads(safe_join(repo_root, rel).read_text(encoding="utf-8"))
    if not isinstance(spec, list) or not spec:
        raise KitError(f"{rel}: patch spec must be a non-empty list")
    for i, p in enumerate(spec):
        f = p.get("file") if isinstance(p, dict) else None
        if not isinstance(f, str) or not f.startswith("gfx/") or "\\" in f or ".." in f:
            raise KitError(f"{rel}: entry {i}: 'file' must be a game-relative gfx/ path")
    return spec


def patched_files(repo_root: Path, game: Path, patch_rels: list) -> dict:
    """{game-relative path: patched bytes} for all specs of one variant.

    Entries for the same file are applied in manifest order, then list order,
    on top of each other; the vanilla file is read from the game install.
    """
    by_file: dict = {}
    for rel in patch_rels:
        for p in load_patch_spec(repo_root, rel):
            by_file.setdefault(p["file"], []).append(p)
    out = {}
    for f in sorted(by_file):
        src = safe_join(game, f)
        if not is_within(src, game) or not src.is_file():
            raise KitError(f"shader patch target {f} not found in the game install")
        text = decode(src.read_bytes())
        out[f] = encode(apply_patch(text, by_file[f]))
    return out
