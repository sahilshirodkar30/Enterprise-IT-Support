class GuardrailBlocked(Exception):
    """A policy rule rejected the input or output. Show a refusal."""


class GuardrailUnavailable(Exception):
    """A safety check could not run. Fail closed and show a degraded message."""