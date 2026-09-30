"""All experiments in build order (EXP-07 last: low priority)."""
from __future__ import annotations

# build IDs that were withdrawn: never built, listed or installed again (P00b-f6: they cut naval regions in pieces)
RETIRED = ("EXP-02b-block-800-sea", "EXP-02b-block-800-land")

# builds whose owner run is done and whose answer is recorded (P00b-f7): still built, listed and checked, so the
# record can be reproduced, but install.py refuses them (running them again cannot tell anything new)
CONCLUDED = {
    "EXP-02b-block-400": "run 2026-09-29 and rejected: the game refused the map for two fractioned naval regions "
                         "(to-check/2026-09-28_exp-results.md)",
    "EXP-08-5632x2560": "run 2026-09-30: crash at hoi4.exe ...8FFB1 after loading, the canvas-size site (P00b log 21)",
    "EXP-08-6144x2560": "run 2026-09-30: the same crash as 5632 (canvas size); its padding also cut 7 vanilla "
                        "wrapping naval regions in pieces (KNOWN_FRACTIONED)",
}

# Naval-region contiguity (naval.py, P00b-f7): fractioned naval regions documented for a concluded build, as
# {build id: {"why": text, "regions": {engine region name: separated sea provinces}}}. naval.judge prints an exact
# match as a note; any other finding, on any build, fails --check.
KNOWN_FRACTIONED = {
    "EXP-02b-block-400": {
        "why": "concluded: the donor remnants cut these two regions; error.log (-debug) 2026-09-29 23:02 listed "
               "exactly these separated provinces",
        "regions": {
            "North East Pacific": [2378, 2404, 2452, 2503, 2551, 2627, 2650, 2676, 2701, 2779],
            "Central North Pacific": [263, 460, 644, 2144, 2252, 2278, 2305, 8583, 9029, 9086],
        }},
    "EXP-08-6144x2560": {
        "why": "concluded: the 512 padding columns at the right end the wrap contact of vanilla's seam-crossing "
               "naval regions; the game logged Bering Sea, West Emperor Chain, North Emperor Chain, ... "
               "(2026-09-30 15:41; the full error.log was not kept)",
        "regions": {
            "Bering Sea": [2526, 2556, 2607, 2656, 2675, 2682, 2700, 2706, 2725, 2748, 2771, 2795, 2820, 2874,
                           2991, 3046, 3052, 3248, 3450, 3591, 3642, 3836, 4043, 5356, 5378, 5782, 5808, 5834,
                           5860, 5886, 5909, 5933, 5957, 5981, 6004, 6271, 6471, 6659, 8170, 8304, 8383, 8608,
                           8636, 8662, 8688, 8713],
            "West Emperor Chain": [5319, 5342, 5638, 5663, 5689, 5715, 5742, 5767, 5794, 5820, 5847, 5897, 5920,
                                   5944, 5968, 5991, 6031, 6228, 6239, 6427, 6438, 6628, 7023, 7740, 8264, 8338,
                                   8365, 8391, 8440, 8494, 8571, 8594, 8620, 8674, 8847, 8873, 8897, 8920, 8943,
                                   9015, 9053],
            "North Emperor Chain": [1264, 2353, 2403],
            "Eastern Micronesia": [2364, 2389, 2414, 2438, 2462, 2487, 2512, 2535, 2852, 2949, 2974, 3014, 5894,
                                   5917, 5941, 5988, 6617, 6820, 7062, 7247, 7287, 7473, 7515, 7699, 8146, 8290,
                                   8316, 8342, 8368, 8369, 8394, 8419, 8470, 8497, 8523, 8547, 8570, 8593, 8619,
                                   8647, 8673, 8699, 8724, 8750, 8773, 8794, 8820, 8846, 8990],
            "Far South Pacific": [5561],
            "West Polynesia": [5460, 5662, 5685, 5688, 5714, 7246, 8145, 8263, 8289, 8315, 8341],
            "Micronesian Gap": [5965, 6019, 7928, 8395, 8420, 8444, 8471, 8498, 8524],
        }},
}


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


def experiment_for(build_id: str):
    """The experiment a build id belongs to (the longest matching experiment id), or None."""
    b = build_id.upper()
    hits = [e for e in experiments() if b.startswith(e.exp_id.upper())]
    return max(hits, key=lambda e: len(e.exp_id)) if hits else None


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
