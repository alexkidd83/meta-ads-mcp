# Codex Adversarial Review Findings (2026-04-08)

From adversarial review of PR #11 (get_ig_profile). These are pre-existing issues, not introduced by the PR.

## 1. [HIGH] Paging URL stripping silently truncates paginated responses

**File:** `meta_ads_mcp/core/api.py` (~lines 189-267)

`make_api_request` applies `_strip_paging_urls` to every response, removing `paging.next`/`paging.previous`. Tools like `list_media` silently return only page 1.

**Fix:** Preserve cursor tokens; strip only the access token from paging URLs. Add regression tests for paginated tools.

**Priority:** Fix before next optimization cycle.

## 2. [MEDIUM] get_media_insights silently falls back to FEED on probe failure

**File:** `meta_ads_mcp/core/instagram_insights.py` (~lines 115-127)

Media-type auto-detection probe doesn't check for API errors. On failure, silently defaults to FEED metrics — wrong for REELS/STORY.

**Fix:** Add `if "error" in type_resp: return json.dumps(type_resp, indent=2)` before `media_product_type` extraction.

**Priority:** Quick fix, do alongside #1.

## 3. [HIGH] publish_media not retry-safe (deferred to Month 2)

**File:** `meta_ads_mcp/core/instagram_insights.py` (~lines 284-307)

Two-step publish (create container → publish) has no idempotency guard. Retry after timeout can create duplicate posts.

**Fix:** Accept/reuse `creation_id`, check container status before creating new. Add partial-failure tests.

**Priority:** Fix before first use of `publish_media` (Month 2, requires S3/R2 video hosting).
