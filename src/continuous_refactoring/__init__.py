from collections.abc import Iterable

from continuous_refactoring import artifacts, agent, cli, git, migrations, phases, planning, prompts, routing, loop


def _reexport(module: object, exported_names: Iterable[str]) -> list[str]:
    names = []
    for name in exported_names:
        globals()[name] = getattr(module, name)
        names.append(name)
    return names


__all__ = [
    *_reexport(artifacts, artifacts.__all__),
    *_reexport(agent, agent.__all__),
    *_reexport(git, git.__all__),
    *_reexport(migrations, migrations.__all__),
    *_reexport(routing, routing.__all__),
    *_reexport(planning, planning.__all__),
    *_reexport(phases, phases.__all__),
    *_reexport(prompts, prompts.__all__),
    *_reexport(loop, loop.__all__),
    *_reexport(cli, cli.__all__),
]
