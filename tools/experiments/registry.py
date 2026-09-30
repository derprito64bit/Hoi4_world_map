"""All experiments in build order (EXP-07 last: low priority)."""
from __future__ import annotations


def experiments():
    from .exp01 import Exp01
    from .exp02 import Exp02
    from .exp02b import Exp02b
    from .exp02c import Exp02c
    from .exp03 import Exp03
    from .exp05 import Exp05
    from .exp06 import Exp06
    from .exp07 import Exp07
    from .exp08 import Exp08
    from .exp09 import Exp09
    exps = [Exp01(), Exp02(), Exp02b(), Exp02c(), Exp03(), Exp05(), Exp06(), Exp07(), Exp08(), Exp09()]
    return sorted(exps, key=lambda e: e.priority)


def resolve(ctx, selector: str):
    """[(experiment, build_id)] for 'all', an experiment ('EXP-03') or one build ('EXP-03-20k')."""
    out = []
    sel = selector.upper()
    for e in experiments():
        for b in e.build_ids(ctx):
            if sel == "ALL" or sel == e.exp_id.upper() or sel == b.upper():
                out.append((e, b))
    if not out:
        raise SystemExit(f"unknown experiment or build id: {selector}")
    return out
