# Plan: Add December 2025 Instagram Metrics to `get_media_insights`

## Context

Live testing on 2026-03-18 confirmed that Meta's Graph API v25.0 supports several new media insight metrics added in December 2025 (`reels_skip_rate`, `reposts`, `ig_reels_avg_watch_time`, `ig_reels_video_view_total_time`, `follows`, `profile_visits`). These are not yet reflected in the official docs but return real data. Our MCP fork currently only defaults to 5 metrics: `reach`, `saved`, `shares`, `views`, `total_interactions`. This plan adds the new metrics so they're available by default where applicable.

**Challenge:** Some new metrics are Reels-specific (prefixed `reels_` or `ig_reels_`). Adding them to the universal defaults would cause 400 errors on IMAGE/CAROUSEL posts.

## Approach

Introduce separate default metric lists by media type (Reels vs. Feed/Carousel vs. Stories), with auto-detection via a preliminary Graph API call. Keep the current simple path working — if the caller passes explicit `metrics`, use them as-is (no detection needed).

## Files to Modify

1. **`meta_ads_mcp/core/instagram_insights.py`** — `get_media_insights` function (lines 52–90)
2. **`tests/test_instagram_insights.py`** — `TestGetMediaInsights` class (lines 126–182)

## Implementation Steps

### Step 1: Update default metric lists in `get_media_insights`

In `instagram_insights.py`, replace the single `default_metrics` with three lists:

```python
FEED_DEFAULT_METRICS = ["reach", "saved", "shares", "views", "total_interactions",
                        "likes", "comments", "follows", "profile_visits", "reposts"]

REELS_DEFAULT_METRICS = FEED_DEFAULT_METRICS + [
    "reels_skip_rate", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"
]

STORY_DEFAULT_METRICS = ["reach", "replies", "taps_forward", "taps_back", "exits",
                         "follows", "profile_visits"]
```

### Step 2: Add media-type auto-detection when using defaults

When `metrics` is `None` (caller wants defaults), make a lightweight Graph API call to fetch the media's `media_product_type`:

```python
if metrics is None:
    # One extra API call to pick the right defaults
    resp = await make_api_request(f"/{media_id}", {"fields": "media_product_type"}, access_token)
    media_type = json.loads(resp).get("media_product_type", "FEED")
    if media_type == "REELS":
        metrics_to_use = REELS_DEFAULT_METRICS
    elif media_type == "STORY":
        metrics_to_use = STORY_DEFAULT_METRICS
    else:
        metrics_to_use = FEED_DEFAULT_METRICS
else:
    metrics_to_use = metrics
```

### Step 3: Update docstring

Update the supported-metrics table in the docstring to include the new metrics:

```
Supported metrics by media type (Graph API v25.0+):
    IMAGE/VIDEO/CAROUSEL (FEED): reach, saved, shares, views, total_interactions,
                                  likes, comments, follows, profile_visits, reposts
    REELS:                       (all FEED metrics) + reels_skip_rate,
                                  ig_reels_avg_watch_time, ig_reels_video_view_total_time
    STORIES:                     reach, replies, taps_forward, taps_back, exits,
                                  follows, profile_visits

Note: reels_skip_rate, reposts, ig_reels_avg_watch_time, ig_reels_video_view_total_time
were added Dec 2025 (not yet in official docs but live on v25.0).
```

### Step 4: Update tests

In `test_instagram_insights.py`:

1. **Update `test_success_with_defaults`** — mock the media-type lookup, assert Reels defaults are used for a REELS media item
2. **Add `test_defaults_for_feed_media`** — mock media_product_type=FEED, assert FEED_DEFAULT_METRICS used
3. **Add `test_defaults_for_story_media`** — mock media_product_type=STORY, assert STORY_DEFAULT_METRICS used
4. **Add `test_custom_metrics_skip_detection`** — when explicit metrics are passed, no media-type lookup is made
5. **Keep existing `test_default_metrics_do_not_include_plays`** — update to check all three default lists

### Step 5: Update `get_story_insights` defaults (bonus)

Add `follows` and `profile_visits` to the story defaults in `get_story_insights` (line ~180) since they're now available for stories too.

## Verification

1. **Unit tests:** `cd /Users/a-mimilidis/dev/projects/gh-atlas-analyzer/repos/meta-ads-mcp && python -m pytest tests/test_instagram_insights.py -v`
2. **Live smoke test — Reels:** `get_media_insights(media_id="18065569718202549")` → should return all 8 Reels metrics including `reels_skip_rate`
3. **Live smoke test — Feed image:** `get_media_insights(media_id="17843740161692860")` → should return feed metrics, NO `reels_skip_rate`
4. **Live smoke test — explicit metrics:** `get_media_insights(media_id="18065569718202549", metrics=["views"])` → only `views`, no auto-detection call
