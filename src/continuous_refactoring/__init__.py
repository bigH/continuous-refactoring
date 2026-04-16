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


_exported_modules = (
    artifacts,
    agent,
    git,
    migrations,
    routing,
    planning,
    phases,
    prompts,
    scope_expansion,
    loop,
    cli,
)

__all__: tuple[str, ...] = ()
_seen_exports: set[str] = set()

for _module in _exported_modules:
    for _name in _module.__all__:
        if _name in _seen_exports:
            raise RuntimeError(f"Duplicate exported symbol in package __init__: {_name!r}")
        globals()[_name] = getattr(_module, _name)
        _seen_exports.add(_name)
    __all__ = (*__all__, *_module.__all__)
