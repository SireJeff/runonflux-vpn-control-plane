"""Unit tests for the isolated_module_load helper (Phase 4.7b).

Uses throwaway dotted names ("zzfake.*") and tmp_path-generated source
files so these tests never touch any real app.* module.
"""
import sys
import types

import pytest

from tests.unit._fdm_isolated_import import isolated_module_load


def _write_module(tmp_path, filename, value):
    path = tmp_path / filename
    path.write_text(f"VALUE = {value!r}\n")
    return path


def test_restores_preexisting_target_module_after_exit(tmp_path):
    """A real module already registered under the target name comes back
    unchanged after the with-block exits."""
    original = types.ModuleType("zzfake.target")
    original.VALUE = "original"
    sys.modules["zzfake.target"] = original

    dummy_path = _write_module(tmp_path, "dummy_a.py", "fresh")

    try:
        with isolated_module_load("zzfake.target", dummy_path) as mod:
            assert mod.VALUE == "fresh"
            assert sys.modules["zzfake.target"] is mod

        assert sys.modules["zzfake.target"] is original
        assert sys.modules["zzfake.target"].VALUE == "original"
    finally:
        del sys.modules["zzfake.target"]


def test_removes_target_module_that_did_not_exist_before(tmp_path):
    """If nothing was registered under the target name before, nothing is
    left registered after the with-block exits."""
    assert "zzfake.absent_target" not in sys.modules

    dummy_path = _write_module(tmp_path, "dummy_b.py", "fresh")

    with isolated_module_load("zzfake.absent_target", dummy_path) as mod:
        assert mod.VALUE == "fresh"
        assert "zzfake.absent_target" in sys.modules

    assert "zzfake.absent_target" not in sys.modules


def test_removes_stub_module_that_did_not_exist_before(tmp_path):
    """module_stubs entries that were absent before are removed after
    exit, even though they were present for the duration of exec_module."""
    assert "zzfake.dep" not in sys.modules

    dep_stub = types.ModuleType("zzfake.dep")
    dummy_path = _write_module(tmp_path, "dummy_c.py", "fresh")

    with isolated_module_load(
        "zzfake.target_c",
        dummy_path,
        module_stubs={"zzfake.dep": dep_stub},
    ):
        assert sys.modules["zzfake.dep"] is dep_stub

    assert "zzfake.dep" not in sys.modules
    assert "zzfake.target_c" not in sys.modules


def test_restores_preexisting_stub_module_after_exit(tmp_path):
    """module_stubs entries that WERE present before are restored to their
    original value, not left as the injected stub."""
    original_dep = types.ModuleType("zzfake.dep2")
    original_dep.VALUE = "real"
    sys.modules["zzfake.dep2"] = original_dep

    fake_dep = types.ModuleType("zzfake.dep2")
    fake_dep.VALUE = "fake"
    dummy_path = _write_module(tmp_path, "dummy_d.py", "fresh")

    try:
        with isolated_module_load(
            "zzfake.target_d",
            dummy_path,
            module_stubs={"zzfake.dep2": fake_dep},
        ):
            assert sys.modules["zzfake.dep2"] is fake_dep

        assert sys.modules["zzfake.dep2"] is original_dep
        assert sys.modules["zzfake.dep2"].VALUE == "real"
    finally:
        del sys.modules["zzfake.dep2"]


def test_restores_preexisting_attribute_after_exit(tmp_path):
    """attr_stubs entries restore the exact prior attribute value on an
    already-real module, not just leave the override in place."""
    real_pkg = types.ModuleType("zzfake.pkg")
    real_pkg.Thing = "real-thing"
    sys.modules["zzfake.pkg"] = real_pkg

    dummy_path = _write_module(tmp_path, "dummy_e.py", "fresh")

    try:
        with isolated_module_load(
            "zzfake.target_e",
            dummy_path,
            attr_stubs={("zzfake.pkg", "Thing"): "fake-thing"},
        ):
            assert sys.modules["zzfake.pkg"].Thing == "fake-thing"

        assert sys.modules["zzfake.pkg"].Thing == "real-thing"
    finally:
        del sys.modules["zzfake.pkg"]


def test_removes_attribute_that_did_not_exist_before(tmp_path):
    """attr_stubs entries for an attribute that was absent before are
    removed entirely after exit, not left set to the stub value."""
    real_pkg = types.ModuleType("zzfake.pkg2")
    sys.modules["zzfake.pkg2"] = real_pkg
    assert not hasattr(real_pkg, "Thing")

    dummy_path = _write_module(tmp_path, "dummy_f.py", "fresh")

    try:
        with isolated_module_load(
            "zzfake.target_f",
            dummy_path,
            attr_stubs={("zzfake.pkg2", "Thing"): "fake-thing"},
        ):
            assert sys.modules["zzfake.pkg2"].Thing == "fake-thing"

        assert not hasattr(sys.modules["zzfake.pkg2"], "Thing")
    finally:
        del sys.modules["zzfake.pkg2"]


def test_restoration_happens_even_if_body_raises(tmp_path):
    """A raise inside the with-block must not leave sys.modules polluted."""
    original = types.ModuleType("zzfake.target_g")
    original.VALUE = "original"
    sys.modules["zzfake.target_g"] = original

    dummy_path = _write_module(tmp_path, "dummy_g.py", "fresh")

    try:
        with pytest.raises(RuntimeError):
            with isolated_module_load("zzfake.target_g", dummy_path):
                raise RuntimeError("boom")

        assert sys.modules["zzfake.target_g"] is original
    finally:
        del sys.modules["zzfake.target_g"]
