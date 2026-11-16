"""Shared helper for FDM test files that load an app module standalone.

Several worker_api/tests/unit/test_fdm_*.py files exec a real app module
(fdm_sync_service.py, fdm_tasks.py) fresh via importlib, registered under
its real dotted name in sys.modules -- required so the module's own
internal relative imports resolve correctly during exec. Without care, this
collection-time sys.modules mutation leaks past the file that made it: any
OTHER test file collected afterward that does a plain
`from app.services.fdm import fdm_sync_service` binds to whatever is left
in sys.modules, which may be an abandoned copy, not the real module.

isolated_module_load() snapshots and restores every sys.modules key and
attribute it touches, so nothing survives past the `with` block.
"""
import importlib.util
import sys
from contextlib import contextmanager

_MISSING = object()


@contextmanager
def isolated_module_load(target_name, file_path, *, module_stubs=None, attr_stubs=None):
    """Load `file_path` fresh under `target_name` in sys.modules.

    module_stubs: dict[str, ModuleType] -- extra sys.modules entries to
        inject for the duration of the load (fake stand-ins for transitive
        dependencies so the target module can be exec'd without a real
        DB/settings/app context). The CALLER decides which dependencies
        need stubbing (e.g. via its own `if X not in sys.modules` guard) --
        this function only applies and restores whatever it's given.
    attr_stubs: dict[tuple[str, str], Any] -- (module_name, attr_name) ->
        value to set on an existing module/package for the duration, for
        callers that need to override one attribute without replacing the
        whole module.

    Yields the freshly loaded module. On exit -- including if the `with`
    body raises -- restores every touched sys.modules key and attribute to
    its exact prior state: deleted if it did not exist before, restored to
    its previous value if it did.
    """
    module_stubs = module_stubs or {}
    attr_stubs = attr_stubs or {}

    touched_modules = set(module_stubs) | {target_name}
    prior_modules = {name: sys.modules.get(name, _MISSING) for name in touched_modules}

    prior_attrs = {}
    for mod_name, attr_name in attr_stubs:
        mod = sys.modules.get(mod_name)
        prior_attrs[(mod_name, attr_name)] = (
            getattr(mod, attr_name, _MISSING) if mod is not None else _MISSING
        )

    try:
        for name, stub in module_stubs.items():
            sys.modules[name] = stub

        for (mod_name, attr_name), value in attr_stubs.items():
            setattr(sys.modules[mod_name], attr_name, value)

        spec = importlib.util.spec_from_file_location(target_name, str(file_path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[target_name] = mod
        spec.loader.exec_module(mod)

        yield mod
    finally:
        for name, prior in prior_modules.items():
            if prior is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

        for (mod_name, attr_name), prior in prior_attrs.items():
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            if prior is _MISSING:
                if hasattr(mod, attr_name):
                    delattr(mod, attr_name)
            else:
                setattr(mod, attr_name, prior)
