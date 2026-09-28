"""Shader patch specs and the EXP-09 manifest (contract: docs/logs/P00b.md section 1)."""
import importlib.util
import json
from pathlib import Path

import pytest

from conftest import REPO
from experiments.common import KitError
from experiments.patchspec import apply_patch, load_manifest, patched_files

TEXT = "float3 A( x ) {\n\treturn x;\n}\nfloat4 B( y ) {\n\treturn y;\n}\n"

# (spec, expected result or None for "must fail") - the same cases run against P00c's reference below
CASES = [
    ([{"anchor": "float4 B(", "mode": "before", "text": "// pre\n"}],
     "float3 A( x ) {\n\treturn x;\n}\n// pre\nfloat4 B( y ) {\n\treturn y;\n}\n"),
    ([{"anchor": "\treturn y;", "mode": "after", "text": " // post"}],
     "float3 A( x ) {\n\treturn x;\n}\nfloat4 B( y ) {\n\treturn y; // post\n}\n"),
    ([{"anchor": "return x;", "mode": "replace", "text": "return x * 0.5;"}],
     "float3 A( x ) {\n\treturn x * 0.5;\n}\nfloat4 B( y ) {\n\treturn y;\n}\n"),
    # sequential: the second anchor is created by the first entry
    ([{"anchor": "return x;", "mode": "replace", "text": "return EXP;"},
      {"anchor": "EXP", "mode": "replace", "text": "x + 1"}],
     "float3 A( x ) {\n\treturn x + 1;\n}\nfloat4 B( y ) {\n\treturn y;\n}\n"),
    ([{"anchor": "missing anchor", "mode": "before", "text": "x"}], None),          # anchor absent
    ([{"anchor": "return", "mode": "before", "text": "x"}], None),                  # anchor twice
    # unique in vanilla, but the first entry duplicates it -> must fail at apply time
    ([{"anchor": "float3 A(", "mode": "after", "text": " float3 A("},
      {"anchor": "float3 A(", "mode": "before", "text": "//"}], None),
    ([{"anchor": "return x;", "mode": "sideways", "text": "x"}], None),             # unknown mode
]


@pytest.mark.parametrize("spec,want", CASES)
def test_apply_patch_cases(spec, want):
    if want is None:
        with pytest.raises(KitError):
            apply_patch(TEXT, spec)
    else:
        assert apply_patch(TEXT, spec) == want


def _p00c_reference():
    path = REPO / "tests" / "gfx" / "test_exp09.py"
    if not path.is_file():
        pytest.skip("P00c's tests/gfx/test_exp09.py not on this branch")
    spec = importlib.util.spec_from_file_location("p00c_test_exp09", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.apply_patch


@pytest.mark.parametrize("spec,want", [c for c in CASES if all(p["mode"] in ("before", "after", "replace") for p in c[0])])
def test_same_semantics_as_p00c_reference(spec, want):
    ref = _p00c_reference()
    try:
        expected = ref(TEXT, spec)
    except AssertionError:
        expected = None
    try:
        got = apply_patch(TEXT, spec)
    except KitError:
        got = None
    assert got == expected


def _write(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((data if isinstance(data, str) else json.dumps(data)).encode("utf-8"))


def fixture_repo(tmp_path, variants, extra_top=None):
    repo = tmp_path / "repo"
    man = {"experiment": "EXP-09", "work_unit": "P00c", "canvas": {"width": 5120}, "install": {"x": "y"},
           "variants": variants}
    if extra_top:
        man.update(extra_top)
    _write(repo / "assets/gfx/FX/experiments/EXP-09/variants.json", man)
    _write(repo / "assets/common/defines/experiments/EXP-09/zz_exp09_a.lua", "NDefines_Graphics.NGraphics.X = 1.0\n")
    _write(repo / "assets/gfx/FX/experiments/EXP-09/p.patch.json",
           [{"file": "gfx/FX/test.shader", "anchor": "return y;", "mode": "replace", "text": "return y * 2;",
             "purpose": "ignored", "behaviour": "ignored"}])
    return repo


V_A = {"id": "a", "label": "base", "changes": "none", "defines": [], "shader_patches": []}
V_B = {"id": "b", "label": "b", "changes": "b", "defines": ["assets/common/defines/experiments/EXP-09/zz_exp09_a.lua"],
       "shader_patches": ["assets/gfx/FX/experiments/EXP-09/p.patch.json"], "unknown_key": 1}


def test_manifest_absent_means_baseline_only(tmp_path):
    assert load_manifest(tmp_path) is None


def test_manifest_ignores_unknown_keys_and_keeps_order(tmp_path):
    repo = fixture_repo(tmp_path, [V_A, V_B, dict(V_B, id="c"), dict(V_B, id="d"), dict(V_B, id="e")])
    vs = load_manifest(repo)
    assert [v.id for v in vs] == ["a", "b", "c", "d", "e"]
    assert vs[1].defines == V_B["defines"]


@pytest.mark.parametrize("variants", [
    [V_B],                                                        # first is not the baseline
    [V_A, dict(V_B, id="a")],                                     # duplicate id
    [V_A, dict(V_B, defines=["assets/missing.lua"])],             # missing source
    [V_A, dict(V_B, defines=["../outside.lua"])],                 # escapes the repo
])
def test_manifest_rejects_bad_input(tmp_path, variants):
    repo = fixture_repo(tmp_path, variants)
    with pytest.raises(KitError):
        load_manifest(repo)


def test_patched_files_reads_game_and_applies(tmp_path):
    repo = fixture_repo(tmp_path, [V_A, V_B])
    game = tmp_path / "game"
    _write(game / "gfx/FX/test.shader", TEXT)
    out = patched_files(repo, game, V_B["shader_patches"])
    assert out == {"gfx/FX/test.shader": TEXT.replace("return y;", "return y * 2;").encode()}
    # the source file in the fake game dir is untouched
    assert (game / "gfx/FX/test.shader").read_text(encoding="utf-8") == TEXT


def test_patched_files_missing_anchor_fails(tmp_path):
    repo = fixture_repo(tmp_path, [V_A, V_B])
    game = tmp_path / "game"
    _write(game / "gfx/FX/test.shader", TEXT.replace("return y;", "return z;"))
    with pytest.raises(KitError):
        patched_files(repo, game, V_B["shader_patches"])


def test_exp09_variant_files_from_fixture_manifest(tmp_path):
    from experiments.base import Ctx
    from experiments.exp09 import Exp09
    repo = fixture_repo(tmp_path, [V_A, V_B])
    game = tmp_path / "game"
    _write(game / "gfx/FX/test.shader", TEXT)
    ctx = Ctx(game=game, vanilla=None, repo_root=repo)
    e = Exp09()
    assert e.build_ids(ctx) == ["EXP-09a", "EXP-09b"]
    assert e.variant_files(ctx, "EXP-09a") == {}
    files = e.variant_files(ctx, "EXP-09b")
    assert set(files) == {"common/defines/zz_exp09_a.lua", "gfx/FX/test.shader"}
    ctx2 = Ctx(game=game, vanilla=None, repo_root=tmp_path / "empty")
    assert e.build_ids(ctx2) == ["EXP-09a"]
