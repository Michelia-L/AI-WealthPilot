"""Pure CME blend shared by live generation and saved-component experiments."""


def blend_assumption(historical: float, forward: float | None, weight: float) -> float:
    """Keep the historical branch when the forward component is unavailable."""
    return (
        historical if forward is None else weight * forward + (1 - weight) * historical
    )
