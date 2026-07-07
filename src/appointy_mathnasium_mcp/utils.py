import base64
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .config import APPOINTY_BOOKING_URL_TEMPLATE, ENABLE_PII_MASKING

def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9+]", "", value)


def _split_email(email: str) -> Tuple[str, str]:
    parts = email.split("@", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def _normalize_email(email: Optional[str]) -> str:
    if not email:
        return ""
    return email.strip().lower()


def _email_variants(email: Optional[str]) -> List[str]:
    normalized = _normalize_email(email)
    if not normalized or "@" not in normalized:
        return []
    local, domain = _split_email(normalized)
    if not local or not domain:
        return [normalized]

    local_no_plus = local.split("+", 1)[0]
    variants = [f"{local_no_plus}@{domain}"]
    if domain in {"gmail.com", "googlemail.com"}:
        variants.append(f"{local_no_plus.replace('.', '')}@{domain}")
    if normalized not in variants:
        variants.insert(0, normalized)

    # Keep order but remove duplicates.
    seen: Set[str] = set()
    deduped = []
    for variant in variants:
        if variant not in seen:
            seen.add(variant)
            deduped.append(variant)
    return deduped


def _mask_email(email: Optional[str]) -> str:
    if not email:
        return ""
    normalized = _normalize_email(email)
    if not ENABLE_PII_MASKING:
        return normalized
    if "@" not in normalized:
        return normalized
    local, domain = _split_email(normalized)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:1]}***{local[-1:]}@{domain}"


def _listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _iter_dict_nodes(value: Any, max_depth: int = 7, depth: int = 0) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _iter_dict_nodes(child, max_depth=max_depth, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                yield from _iter_dict_nodes(item, max_depth=max_depth, depth=depth + 1)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return _to_text(value)


def _gcp_filter_string(value: Any) -> str:
    text = _to_text(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')



def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _to_text(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.year <= 1:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _normalize_log_timestamp(value: Optional[str], *, default: datetime) -> str:
    if not value:
        return default.isoformat().replace("+00:00", "Z")
    parsed = _parse_datetime(value)
    if parsed is None:
        return default.isoformat().replace("+00:00", "Z")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _compact_payload(value: Any, *, include_payload: bool) -> Any:
    if not include_payload:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return _to_text(value)


def _decode_base64_json(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _build_booking_urls(location_slug: str, company_slug: str = "") -> List[str]:
    urls: List[str] = []
    template = APPOINTY_BOOKING_URL_TEMPLATE.strip()
    if template and "{locationSlug}" in template:
        try:
            built = template.format(
                locationSlug=location_slug,
                companySlug=company_slug,
                slug=location_slug,
            )
            if built:
                urls.append(built)
        except Exception:
            pass

    # Safe fallback candidates when template is not supplied or mismatched.
    if location_slug:
        urls.append(f"https://www.appointy.com/{location_slug}")
    if company_slug:
        urls.append(f"https://www.appointy.com/{company_slug}")

    deduped = []
    seen = set()
    for url in urls:
        cleaned = url.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _unique_by_key(rows: List[Dict[str, Any]], key_fields: List[str]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = tuple(_to_text(row.get(field, "")).lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _status_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"active", "enabled", "true", "yes"}:
            return True
        if cleaned in {"inactive", "disabled", "false", "no"}:
            return False
    return None

