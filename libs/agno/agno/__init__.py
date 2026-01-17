from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agno")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]

# Optional prompt versioning module (requires mlflow)
try:
    from agno import prompt_versioning
    __all__.append("prompt_versioning")
except ImportError:
    pass
