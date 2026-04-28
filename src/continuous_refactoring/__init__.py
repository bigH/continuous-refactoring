from __future__ import annotations

from types import ModuleType

from continuous_refactoring import agent
from continuous_refactoring import artifacts
from continuous_refactoring import cli
from continuous_refactoring import decisions
from continuous_refactoring import failure_report
from continuous_refactoring import git
from continuous_refactoring import loop
from continuous_refactoring import migration_tick
from continuous_refactoring import migrations
from continuous_refactoring import phases
from continuous_refactoring import planning
from continuous_refactoring import prompts
from continuous_refactoring import routing
from continuous_refactoring import routing_pipeline
from continuous_refactoring import scope_candidates
from continuous_refactoring import scope_expansion

_PACKAGE_EXPORT_MODULES: tuple[ModuleType, ...] = (
    agent,
    artifacts,
    cli,
    decisions,
    failure_report,
    git,
    loop,
    migration_tick,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    routing_pipeline,
    scope_candidates,
    scope_expansion,
)
_SUBMODULES: tuple[ModuleType, ...] = _PACKAGE_EXPORT_MODULES


def collect_package_exports(modules: tuple[ModuleType, ...]) -> tuple[str, ...]:
    exports: list[str] = []
    exporters: dict[str, str] = {}
    for module in modules:
        module_name = module.__name__
        for name in module.__all__:
            if name in exporters:
                raise RuntimeError(
                    "Duplicate exported symbol in package __init__: "
                    f"{name!r} (original module: {exporters[name]}, "
                    f"conflicting module: {module_name})"
                )
            exporters[name] = module_name
            globals()[name] = getattr(module, name)
            exports.append(name)
    return tuple(exports)


def _stabilize_package_export_order(exports: tuple[str, ...]) -> tuple[str, ...]:
    names = list(exports)
    describe_index = names.index("describe_scope_candidate")
    names.pop(describe_index)
    scope_selection_index = names.index("ScopeSelection")
    names.insert(scope_selection_index + 1, "describe_scope_candidate")
    return tuple(names)


__all__: tuple[str, ...] = _stabilize_package_export_order(
    collect_package_exports(_SUBMODULES)
)
