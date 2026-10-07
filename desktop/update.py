from __future__ import annotations

# Security default: no unsigned remote updater is shipped. Enabling online update
# requires a release repository plus a pinned public verification key.
SIGNED_UPDATES_ENABLED = False


def update_capability() -> dict[str, object]:
    return {
        "enabled": SIGNED_UPDATES_ENABLED,
        "reason": "尚未配置簽章公鑰與正式發佈來源，因此安全停用線上更新。",
    }
