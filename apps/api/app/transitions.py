"""Allowed status moves for service orders and material orders.

A move is accepted only when the actor, the current status, and the next
status are listed together. Every other combination is a conflict (HTTP 409).
"""

from __future__ import annotations

# actor, from_status, to_status
# client — the customer who placed the order
# provider — the assigned specialist, or the material supplier
# staff — admin or moderator

SERVICE_ORDER_TRANSITIONS: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("provider", "requested", "quoted"),
        ("staff", "requested", "quoted"),
        ("client", "requested", "cancelled"),
        ("provider", "requested", "cancelled"),
        ("staff", "requested", "cancelled"),
        ("client", "quoted", "accepted"),
        ("staff", "quoted", "accepted"),
        ("client", "quoted", "cancelled"),
        ("provider", "quoted", "cancelled"),
        ("staff", "quoted", "cancelled"),
        ("provider", "accepted", "in_progress"),
        ("staff", "accepted", "in_progress"),
        ("client", "accepted", "cancelled"),
        ("provider", "accepted", "cancelled"),
        ("staff", "accepted", "cancelled"),
        ("provider", "in_progress", "completed"),
        ("staff", "in_progress", "completed"),
        ("client", "in_progress", "cancelled"),
        ("provider", "in_progress", "cancelled"),
        ("staff", "in_progress", "cancelled"),
    }
)

MATERIAL_ORDER_TRANSITIONS: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("provider", "requested", "confirmed"),
        ("staff", "requested", "confirmed"),
        ("provider", "confirmed", "shipped"),
        ("staff", "confirmed", "shipped"),
        ("provider", "shipped", "delivered"),
        ("staff", "shipped", "delivered"),
        ("client", "requested", "cancelled"),
        ("provider", "requested", "cancelled"),
        ("staff", "requested", "cancelled"),
        ("client", "confirmed", "cancelled"),
        ("provider", "confirmed", "cancelled"),
        ("staff", "confirmed", "cancelled"),
        ("provider", "shipped", "cancelled"),
        ("staff", "shipped", "cancelled"),
    }
)


class ConflictError(Exception):
    def __init__(self) -> None:
        super().__init__("Этот переход статуса недоступен")


def assert_transition(
    table: frozenset[tuple[str, str, str]],
    actor: str,
    current: str,
    target: str,
) -> None:
    if (actor, current, target) not in table:
        raise ConflictError()
