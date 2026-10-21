"""Hand-off to the registration agent's inbox.

TODO(registration): request_recipients and the supplier «Входящие» inbox are
owned by the registration branch. This hook is the only integration point.
Do not build that inbox here. Drop recipient_stub when their model lands.
"""

from __future__ import annotations


def on_request_sent(request_id: str, company_ids: list[str]) -> None:
    """Recipients are already stored. The inbox reads them on the other branch."""
    del request_id, company_ids


def on_offer_selected(request_id: str, offer_id: str, project_id: str | None) -> None:
    """TODO: copy the chosen offer into the project procurement sheet."""
    del request_id, offer_id, project_id
