from types import ModuleType

from . import (
    agent,
    artifacts,
    cli,
    decisions,
    failure_report,
    git,
    loop,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    routing_pipeline,
    scope_expansion,
)

_SUBMODULES: tuple[ModuleType, ...] = (
    agent,
    artifacts,
    cli,
    decisions,
    failure_report,
    git,
    loop,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    routing_pipeline,
    scope_expansion,
)


def _reexport() -> tuple[str, ...]:
    exports: list[str] = []
    for module in _SUBMODULES:
        for name in module.__all__:
            if name in exports:
                raise RuntimeError(
                    f"Duplicate exported symbol in package __init__: {name!r}"
                )
            globals()[name] = getattr(module, name)
            exports.append(name)
    return tuple(exports)


__all__: tuple[str, ...] = _reexport()
