"""Test configuration: filter third-party warnings that are out of our control."""
import warnings

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings(
        "ignore",
        category=LangChainPendingDeprecationWarning,
        message="The default value of `allowed_objects`",
    )
except ImportError:
    pass