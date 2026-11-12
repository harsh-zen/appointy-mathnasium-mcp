"""Resolve exact Appointy IDs without trusting cache completeness."""

from .config import MATHNASIUM_GROUP_ID


def checked_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("An entity ID is required.")
    if "/" in value and value.split("/")[0] != MATHNASIUM_GROUP_ID:
        raise ValueError("Entity ID belongs to a different group.")
    return value


def company_id(value: str) -> str:
    value = checked_id(value)
    parts = value.split("/")
    if len(parts) == 1 and value.startswith("com_"):
        return f"{MATHNASIUM_GROUP_ID}/{value}"
    if len(parts) >= 2 and parts[1].startswith("com_"):
        return "/".join(parts[:2])
    raise ValueError("Expected a company ID or a full company-scoped ID.")


async def full_id(value: str, *, company: str = None, parent: str = None) -> str:
    value = checked_id(value)
    if "/" in value:
        return value
    if value.startswith("com_"):
        return company_id(value)
    if value.startswith("loc_"):
        if company:
            return f"{company_id(company)}/{value}"
        from .domain import _get_group_context_cached

        context = await _get_group_context_cached()
        matches = [
            r["locationId"]
            for r in context.get("centerIndex", [])
            if r.get("locationId", "").split("/")[-1] == value
        ]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(
            "Short location ID needs companyId or a unique center lookup result."
        )
    if value.startswith(("stu_", "cust_", "emp_")) and company:
        return f"{company_id(company)}/{value}"
    if value.startswith(("srv_", "apt_", "res_")) and parent:
        return f"{checked_id(parent)}/{value}"
    raise ValueError("Supply the full entity ID, or its company/location parent scope.")
