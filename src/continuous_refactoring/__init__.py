from types import ModuleType

from . import (
    agent,
    artifacts,
    cli,
    git,
    loop,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    scope_expansion,
)


def _reexport(*modules: ModuleType) -> tuple[str, ...]:
    exports: list[str] = []
    seen: set[str] = set()
    for module in modules:
        for name in module.__all__:
            if name in seen:
                raise RuntimeError(
                    f"Duplicate exported symbol in package __init__: {name!r}"
                )
            globals()[name] = getattr(module, name)
            seen.add(name)
            exports.append(name)
    return tuple(exports)


__all__: tuple[str, ...] = _reexport(
    agent,
    artifacts,
    cli,
    git,
    loop,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    scope_expansion,
)
