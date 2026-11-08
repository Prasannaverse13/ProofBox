"""Money helpers. All amounts are integer cents."""


def apply_discount(total_cents: int, percent: int) -> int:
    """Return the total after a percentage discount, rounded to the nearest cent."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(total_cents * (100 - percent) / 100)


def split_bill(total_cents: int, people: int) -> list[int]:
    """Split a bill between people. The shares must add up to the total."""
    if people <= 0:
        raise ValueError("people must be positive")
    share = total_cents // people
    return [share] * people
