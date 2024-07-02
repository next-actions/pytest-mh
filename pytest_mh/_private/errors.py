from __future__ import annotations


class ArtifactsExceptionGroup(ExceptionGroup):
    """
    One or more exception occurred during artifacts collection.
    """

    ...


class TeardownExceptionGroup(ExceptionGroup):
    """
    One or more exception occurred during teardown phase.
    """

    ...
