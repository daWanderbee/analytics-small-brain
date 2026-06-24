"""
Meta (WhatsApp + Instagram + Facebook + Ads) data module for the CHUK dashboard.
Reads creds from a gitignored meta_secrets.json — never hardcode tokens.

Every fetch returns (data, error): error is None on success, else a string.
So the UI can show a clean "needs setup / reconnect" card instead of crashing.
"""
import json, os, time, urllib.request, urllib.parse

GRAPH = "https://graph.facebook.com/v21.0"
HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(HERE, "meta_secrets.json")


def load_meta():
    """Load creds. Returns (dict, error). Prefers Streamlit Cloud secrets, falls back to local file."""
    try:
        import streamlit as st
        if "meta" in st.secrets:
            return dict(st.secrets["meta"]), None
    except Exception:
        pass
    if not os.path.exists(SECRETS):
        return None, "meta_secrets.json missing — copy meta_secrets.example.json and fill it in."
    try:
        return json.load(open(SECRETS)), None
    except Exception as e:
        return None, f"meta_secrets.json invalid JSON: {e}"


def _get(path, params, token):
    params = dict(params or {})
    params["access_token"] = token
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {}).get("message", str(e))
        except Exception:
            err = str(e)
        return None, err
    except Exception as e:
        return None, str(e)


# ── WHATSAPP ──────────────────────────────────────────────────────────
def wa_quality(cfg):
    """Phone number quality + messaging limit tier."""
    pid = cfg.get("phone_number_id"); tok = cfg.get("access_token")
    if not (pid and tok):
        return None, "phone_number_id / access_token not set"
    return _get(pid, {"fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier"}, tok)


def wa_analytics(cfg, days=30):
    """Messages sent/delivered per day (WABA messaging analytics)."""
    waba = cfg.get("waba_id"); tok = cfg.get("access_token")
    if not (waba and tok):
        return None, "waba_id / access_token not set"
    end = int(time.time()); start = end - days * 86400
    fields = f"analytics.start({start}).end({end}).granularity(DAY)"
    data, err = _get(waba, {"fields": fields}, tok)
    if err:
        return None, err
    return data.get("analytics", {}), None


def wa_conversations(cfg, days=30):
    """Conversation counts + cost by category (free vs paid)."""
    waba = cfg.get("waba_id"); tok = cfg.get("access_token")
    if not (waba and tok):
        return None, "waba_id / access_token not set"
    end = int(time.time()); start = end - days * 86400
    fields = (f"conversation_analytics.start({start}).end({end}).granularity(DAILY)"
              f".dimensions(['CONVERSATION_CATEGORY','CONVERSATION_TYPE'])")
    data, err = _get(waba, {"fields": fields}, tok)
    if err:
        return None, err
    return data.get("conversation_analytics", {}).get("data", []), None


def wa_templates(cfg, limit=50):
    """List message templates (id, name, status, category). Returns (list, error)."""
    waba = cfg.get("waba_id"); tok = cfg.get("access_token")
    if not (waba and tok):
        return None, "waba_id / access_token not set"
    data, err = _get(f"{waba}/message_templates",
                     {"fields": "id,name,status,category", "limit": limit}, tok)
    if err:
        return None, err
    return data.get("data", []), None


def wa_template_analytics(cfg, template_ids, days=30):
    """Per-template sent/delivered/read/clicked → real CTR. Returns (list, error).
    template_ids: list of up to 10 template id strings."""
    waba = cfg.get("waba_id"); tok = cfg.get("access_token")
    if not (waba and tok):
        return None, "waba_id / access_token not set"
    if not template_ids:
        return [], None
    end = int(time.time()); start = end - days * 86400
    params = {
        "fields": "template_analytics",
        "start": start, "end": end, "granularity": "DAILY",
        "metric_types": json.dumps(["SENT", "DELIVERED", "READ", "CLICKED"]),
        "template_ids": json.dumps(template_ids[:10]),
    }
    data, err = _get(f"{waba}/template_analytics", params, tok)
    if err:
        return None, err
    # Response: {"data": [{"granularity":..., "data_points":[...]}], ...}
    # data_points are empty until analytics is enabled in WhatsApp Manager.
    rows = data.get("data", [])
    if not rows:
        return [], None
    return rows[0].get("data_points", []), None


# ── INSTAGRAM ─────────────────────────────────────────────────────────
def ig_profile(cfg):
    ig = cfg.get("ig_user_id"); tok = cfg.get("access_token")
    if not (ig and tok):
        return None, "ig_user_id not set (get it in Meta dashboard → linked IG account)"
    return _get(ig, {"fields": "username,followers_count,media_count,profile_picture_url"}, tok)


def ig_insights(cfg, days=30):
    ig = cfg.get("ig_user_id"); tok = cfg.get("access_token")
    if not (ig and tok):
        return None, "ig_user_id not set"
    end = int(time.time()); start = end - days * 86400
    return _get(f"{ig}/insights",
                {"metric": "reach,accounts_engaged", "metric_type": "total_value",
                 "period": "day", "since": start, "until": end}, tok)


def ig_top_media(cfg, limit=8):
    ig = cfg.get("ig_user_id"); tok = cfg.get("access_token")
    if not (ig and tok):
        return None, "ig_user_id not set"
    return _get(f"{ig}/media",
                {"fields": "caption,media_type,permalink,like_count,comments_count,timestamp",
                 "limit": limit}, tok)


# ── FACEBOOK PAGE ─────────────────────────────────────────────────────
def _page_token(cfg):
    """Resolve a Page access token. Page insights require it (not a user/system token)."""
    if cfg.get("page_access_token"):
        return cfg["page_access_token"]
    page = cfg.get("page_id"); tok = cfg.get("access_token")
    if not (page and tok):
        return None
    data, err = _get("me/accounts", {"fields": "id,access_token"}, tok)
    if err or not data:
        return None
    for p in data.get("data", []):
        if p.get("id") == page:
            return p.get("access_token")
    return None


def fb_insights(cfg, days=30):
    """Page profile (followers) + engagement metrics. Returns (dict, error).
    Uses valid post-2024 metrics; older page_impressions/page_fans are deprecated."""
    page = cfg.get("page_id")
    if not page:
        return None, "page_id not set"
    pat = _page_token(cfg)
    if not pat:
        return None, "could not get a Page access token (need pages_show_list + page assigned to the user)"
    # Follower/fan count from the page node (insights metrics for these are deprecated).
    node, err = _get(page, {"fields": "name,fan_count,followers_count"}, pat)
    if err:
        return None, err
    preset = {7: "last_7d", 30: "last_30d", 90: "last_90d"}.get(days, "last_30d")
    metrics = "page_post_engagements,page_views_total,page_daily_follows"
    ins, ins_err = _get(f"{page}/insights",
                        {"metric": metrics, "period": "day", "date_preset": preset}, pat)
    totals = {}
    if not ins_err and ins:
        for row in ins.get("data", []):
            totals[row.get("name")] = sum(pt.get("value", 0) or 0 for pt in row.get("values", []))
    return {
        "name": node.get("name"),
        "followers": node.get("followers_count", node.get("fan_count", 0)),
        "engagements": totals.get("page_post_engagements", 0),
        "views": totals.get("page_views_total", 0),
        "new_follows": totals.get("page_daily_follows", 0),
    }, None


# ── META ADS ──────────────────────────────────────────────────────────
def ads_insights(cfg, date_preset="last_30d"):
    acct = cfg.get("ad_account_id"); tok = cfg.get("access_token")
    if not (acct and tok):
        return None, "ad_account_id not set (needs ads_read scope)"
    acct = acct if str(acct).startswith("act_") else f"act_{acct}"
    return _get(f"{acct}/insights",
                {"fields": "campaign_name,spend,impressions,clicks,ctr,cpc,actions",
                 "level": "campaign", "date_preset": date_preset, "limit": 50}, tok)
