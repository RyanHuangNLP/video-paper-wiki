"""Resolve Hermes adapters by platform identity. No credential logging."""

DELIVERY_OK = "ok"
DELIVERY_MISSING = "missing_adapter"
DELIVERY_AMBIGUOUS = "ambiguous_adapter"
DELIVERY_EXCEPTION = "send_exception"
DELIVERY_UNSUCCESSFUL = "send_unsuccessful"
DELIVERY_SKIPPED = "skipped"
DELIVERY_NO_PAYLOAD = "no_payload"
DELIVERY_NO_MENTION = "no_mention"

DELIVERY_STATUSES = frozenset(
    {
        DELIVERY_OK,
        DELIVERY_MISSING,
        DELIVERY_AMBIGUOUS,
        DELIVERY_EXCEPTION,
        DELIVERY_UNSUCCESSFUL,
        DELIVERY_SKIPPED,
        DELIVERY_NO_PAYLOAD,
        DELIVERY_NO_MENTION,
    }
)


def platform_identity(value):
    if value is None:
        return None
    inner = getattr(value, "value", value)
    if inner is None:
        return None
    if not isinstance(inner, str):
        inner = str(inner)
    text = inner.strip().lower()
    return text or None


def resolve_adapter(gateway, platform):
    want = platform_identity(platform)
    if gateway is None or want is None:
        return None, DELIVERY_MISSING
    adapters = getattr(gateway, "adapters", None)
    if not isinstance(adapters, dict) or not adapters:
        return None, DELIVERY_MISSING
    if platform in adapters:
        adapter = adapters.get(platform)
        if adapter is None:
            return None, DELIVERY_MISSING
        return adapter, None
    matches = []
    for key, adapter in adapters.items():
        if platform_identity(key) != want:
            continue
        if adapter is None:
            continue
        matches.append(adapter)
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, DELIVERY_AMBIGUOUS
    return None, DELIVERY_MISSING


def delivery_token(status):
    if status in DELIVERY_STATUSES:
        return status
    return DELIVERY_UNSUCCESSFUL


def send_result_mentions(result):
    if result is None:
        return []
    mentions = getattr(result, "mentions", None)
    if mentions is None:
        raw = getattr(result, "raw", None)
        if isinstance(raw, dict):
            mentions = raw.get("mentions")
        elif raw is not None:
            mentions = getattr(raw, "mentions", None)
    if not mentions:
        return []
    if isinstance(mentions, (list, tuple)):
        return [item for item in mentions if item]
    return [mentions]
