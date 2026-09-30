#!/usr/bin/env python3
"""Install / uninstall one built experiment as a launcher mod (owner runs this, never an agent).

    python tools/experiments/install.py EXP-03-20k             write $HOI4_USER_DIR/mod/p00b_EXP-03-20k.mod
    python tools/experiments/install.py EXP-03-20k --uninstall remove that file again
    python tools/experiments/install.py EXP-03-20k --dry-run   print what would be written (or deleted)

The only file ever written or deleted is ``$HOI4_USER_DIR/mod/p00b_<ID>.mod``
(keys as in the build's descriptor.mod plus an absolute ``path=`` to
``build/experiments/<ID>``). Every other destination is refused (paths are
resolved, symlinks included, and must stay inside ``$HOI4_USER_DIR/mod``).
dlc_load.json and playsets are never touched: tick the mod in the launcher.
Retired and concluded builds (``registry.RETIRED`` / ``registry.CONCLUDED``) are refused.

The Paradox launcher rewrites these files (drops comments, reorders keys, no
final newline), so an existing file counts as written by this kit only when
all of these hold (``kit_file_problem``): the file name is ``p00b_<ID>.mod``,
its ``path=`` resolves to this repository's ``build/experiments/<ID>`` and its
``name=`` is ``P00b <ID>`` or starts with ``P00b <ID> ``. Any other file is
never overwritten or deleted.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import BUILD_ROOT, KitError, is_within, user_dir  # noqa: E402
from experiments.registry import CONCLUDED, RETIRED  # noqa: E402

BUILD_ID = re.compile(r"^EXP-\d\d[A-Za-z0-9-]{0,24}$")
USER_DIR_MARKERS = ("settings.txt", "dlc_load.json")    # files the game writes into its user folder


def mod_file_name(build_id: str) -> str:
    if not BUILD_ID.match(build_id):
        raise KitError(f"not an experiment build id: {build_id!r}")
    return f"p00b_{build_id}.mod"


def target_path(user: Path, build_id: str) -> Path:
    """$HOI4_USER_DIR/mod/p00b_<ID>.mod, refusing anything that resolves elsewhere."""
    if user is None:
        raise KitError("HOI4_USER_DIR is not set (see .claude/settings.local.json)")
    user = Path(user)
    if not user.is_dir():
        raise KitError(f"HOI4_USER_DIR {user} does not exist")
    if not any((user / m).is_file() for m in USER_DIR_MARKERS):
        raise KitError(f"HOI4_USER_DIR {user} does not look like a Hearts of Iron IV user folder "
                       f"(none of {', '.join(USER_DIR_MARKERS)} found); refusing to write there")
    moddir = user / "mod"
    if moddir.exists() and not is_within(moddir, user):
        raise KitError(f"{moddir} resolves outside {user}; refusing")
    name = mod_file_name(build_id)
    dest = moddir / name
    if dest.resolve().parent != moddir.resolve() or not is_within(dest, user):
        raise KitError(f"{dest} resolves outside {moddir}; refusing")
    return dest


def launcher_text(build_dir: Path) -> str:
    """descriptor.mod keys (comment lines dropped) plus an absolute path= to the build folder."""
    desc = build_dir / "descriptor.mod"
    if not desc.is_file():
        raise KitError(f"{build_dir} is not built (no descriptor.mod); run tools/experiments/build.py first")
    lines = [ln for ln in desc.read_text(encoding="utf-8").splitlines()
             if not ln.startswith("path=") and not ln.lstrip().startswith("#")]
    path = build_dir.resolve().as_posix()
    return "\n".join(lines + [f'path="{path}"']) + "\n"


# ---------------------------------------------------------------- recognising kit files
_TOKEN = re.compile(r'"[^"\n]*"|[{}=]|#[^\n]*|[^\s{}="#]+|\s+')


def parse_top_level(text: str) -> dict:
    """{key: [values]} for the top-level ``key=value`` pairs of a launcher .mod file.

    Tolerant of any key order, tabs, CRLF, a BOM and a missing final newline.
    ``#`` comments are skipped; a block value (``tags={...}``) is recorded as
    ``None``. Raises KitError on text that does not tokenise or nest.
    """
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    toks, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise KitError(f"cannot parse the .mod file near {text[pos:pos + 20]!r}")
        pos = m.end()
        t = m.group(0)
        if not t.isspace() and not t.startswith("#"):
            toks.append(t)
    out, depth, i = {}, 0, 0
    while i < len(toks):
        t = toks[i]
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1
            if depth < 0:
                raise KitError("unbalanced '}' in the .mod file")
        elif depth == 0 and t != "=" and i + 1 < len(toks) and toks[i + 1] == "=":
            v = toks[i + 2] if i + 2 < len(toks) else None
            if v is None or v in ("}", "="):
                raise KitError(f"key {t!r} has no value in the .mod file")
            if v == "{":
                out.setdefault(t, []).append(None)
                i += 2                                   # the '{' itself is counted next round
                continue
            out.setdefault(t, []).append(v[1:-1] if v.startswith('"') else v)
            i += 3
            continue
        i += 1
    if depth != 0:
        raise KitError("unbalanced '{' in the .mod file")
    return out


def kit_file_problem(dest: Path, build_id: str, user: Path, build_root: Path = BUILD_ROOT) -> str | None:
    """None if ``dest`` is a launcher .mod file of this kit for ``build_id``; else why it is not.

    All must hold: the file name is ``p00b_<ID>.mod``; it is a regular file (no symlink);
    exactly one top-level ``path=`` resolving to ``<build_root>/<ID>``; exactly one
    top-level ``name=`` equal to ``P00b <ID>`` or starting with ``P00b <ID> ``.
    """
    dest = Path(dest)
    if dest.name != mod_file_name(build_id):
        return f"file name is not {mod_file_name(build_id)}"
    if dest.is_symlink() or not dest.is_file():
        return "not a regular file"
    try:
        kv = parse_top_level(dest.read_bytes().decode("utf-8", errors="replace"))
    except (OSError, KitError) as e:
        return str(e)
    paths, names = kv.get("path", []), kv.get("name", [])
    if len(paths) != 1 or paths[0] is None:
        return "no single path= entry"
    if len(names) != 1 or names[0] is None:
        return "no single name= entry"
    want = (Path(build_root) / build_id).resolve()
    p = Path(paths[0])
    if not p.is_absolute():
        p = Path(user) / p                     # a relative launcher path is relative to the user folder
    try:
        same = p.resolve() == want
    except (OSError, ValueError):
        same = False
    if not same:
        return f"path={paths[0]!r} is not {want.as_posix()}"
    prefix = f"P00b {build_id}"
    if not (names[0] == prefix or names[0].startswith(prefix + " ")):
        return f"name={names[0]!r} does not start with {prefix!r}"
    return None


def is_kit_file(dest: Path, build_id: str, user: Path, build_root: Path = BUILD_ROOT) -> bool:
    return kit_file_problem(dest, build_id, user, build_root) is None


# ---------------------------------------------------------------- install / uninstall
def install(build_id: str, user: Path, build_root: Path = BUILD_ROOT, dry_run: bool = False) -> Path:
    if build_id in RETIRED:                     # a stale folder may still exist below build/experiments
        raise KitError(f"{build_id} is retired (see tools/experiments/registry.py RETIRED); it must not be run")
    if build_id in CONCLUDED:                   # P00b-f7: the owner run is done and recorded
        raise KitError(f"{build_id} is concluded ({CONCLUDED[build_id]}; see tools/experiments/registry.py "
                       "CONCLUDED); it must not be run again")
    dest = target_path(user, build_id)
    build_dir = Path(build_root) / build_id
    if not is_within(build_dir, build_root):
        raise KitError("build folder outside the build root")
    text = launcher_text(build_dir)
    if dest.exists() or dest.is_symlink():
        why = kit_file_problem(dest, build_id, user, build_root)
        if why:
            raise KitError(f"{dest} exists and was not written by this kit ({why}); refusing to overwrite")
    if not dry_run:
        dest.parent.mkdir(exist_ok=True)
        if not is_within(dest.parent, user):
            raise KitError("mod folder resolves outside the user directory; refusing")
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return dest


def uninstall(build_id: str, user: Path, dry_run: bool = False, build_root: Path = BUILD_ROOT) -> Path | None:
    dest = target_path(user, build_id)
    if not dest.exists() and not dest.is_symlink():
        return None
    why = kit_file_problem(dest, build_id, user, build_root)
    if why:
        raise KitError(f"{dest} was not written by this kit ({why}); refusing to delete")
    if not dry_run:
        dest.unlink()
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build_id", help="e.g. EXP-01A, EXP-03-20k, EXP-09c")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.uninstall:
            p = uninstall(a.build_id, user_dir(), a.dry_run, build_root=BUILD_ROOT)
            if p is None:
                print("nothing to remove")
            else:
                print(("would delete " if a.dry_run else "removed ") + str(p))
        else:
            p = install(a.build_id, user_dir(), build_root=BUILD_ROOT, dry_run=a.dry_run)
            print(("would write " if a.dry_run else "wrote ") + str(p))
            print("Now open the Paradox launcher, add the mod to an empty playset and tick it.")
    except KitError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
