"""Role permissions for sign-up.

`contractor` is исполнитель услуг. It is not `foreman` and does not receive
foreman permissions.

A customer or contractor is also `owner` of the new company (see
company_members). That membership, not a foreman mapping, is what lets them
create an object.

Phone sign-up stays pending with access level `none`: no session is issued
and protected routes treat the account as absent. `phone_verified_at` stays
empty, so the partial unique phone index does not reserve the number.
"""

FOREMAN_PERMISSIONS = frozenset({"site.field", "site.daily"})

ROLE_PERMISSIONS = {
    "supplier": frozenset({"profile.self", "catalog.self", "inbox.self"}),
    "contractor": frozenset({"profile.self", "services.self", "projects.create"}),
    "customer": frozenset({"profile.self", "orders.self", "projects.create"}),
    "foreman": FOREMAN_PERMISSIONS,
    "owner": frozenset({"profile.self", "projects.create", "orders.self"}),
    "admin": frozenset({"profile.self", "projects.create", "moderation"}),
}

PHONE_PENDING_ACCESS = "none"
SIGNUP_ROLES = ("supplier", "contractor", "customer")


def permissions_for(role: str, *, status: str = "active") -> frozenset[str]:
    if status != "active":
        return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())
