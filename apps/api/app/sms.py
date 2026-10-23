"""SMS delivery.

The live adapter is disabled. Nothing here contacts a provider, places an order,
or writes a verification code to a log.
"""

from typing import Protocol


class SmsAdapter(Protocol):
    def send_code(self, phone: str, code: str) -> None:
        """Deliver a verification code. Implementations must not log the code."""


class DisabledSmsAdapter:
    """Live SMS is off."""

    def send_code(self, phone: str, code: str) -> None:
        _ = (phone, code)
        raise RuntimeError("SMS delivery is disabled")


def sms_adapter() -> SmsAdapter:
    return DisabledSmsAdapter()


def live_sms_enabled() -> bool:
    """Real delivery stays off. Demo sign-up uses the on-screen stub instead."""
    return False
