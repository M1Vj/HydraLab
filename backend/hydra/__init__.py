"""Public HydraLab API without starting application setup on package import."""

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from hydra.app import create_app

        globals()[name] = create_app
        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
