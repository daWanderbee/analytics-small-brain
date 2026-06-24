"""
CHUK WhatsApp platform client — pulls the campaign funnel (sent/delivered/read/failed)
from the in-house sender API (campaign_recipients), since WhatsApp's own API has no
per-template history. CTA clicks come separately from GA4 UTM; this is the delivery side.

Creds live in a gitignored platform_secrets.json (or st.secrets["platform"]). Use a
READ-ONLY analytics account, never an admin login.

Every call returns (data, error): error is None on success, else a string.
"""
import json, os, time, urllib.request, urllib.parse, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(HERE, "platform_secrets.json")

_TOKEN_CACHE = {"token": None, "exp": 0}


def load_platform():
    """Load creds. Prefers Streamlit secrets, falls back to local file. Returns (dict, error)."""
    try:
        import streamlit as st
        if "platform" in st.secrets:
            return dict(st.secrets["platform"]), None
    except Exception:
        pass
    if not os.path.exists(SECRETS):
        return None, "platform_secrets.json missing — copy platform_secrets.example.json and fill it in."
    try:
        return json.load(open(SECRETS)), None
    except Exception as e:
        return None, f"platform_secrets.json invalid JSON: {e}"


def _req(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)
            msg = msg.get("message") or msg.get("error") or str(msg)
        except Exception:
            msg = str(e)
        return None, f"{e.code}: {msg}"
    except Exception as e:
        return None, str(e)


def login(cfg):
    """Get a JWT (cached ~6 days; token is valid 7). Returns (token, error)."""
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["exp"] > now:
        return _TOKEN_CACHE["token"], None
    base = (cfg.get("base_url") or "").rstrip("/")
    email = cfg.get("email"); pw = cfg.get("password")
    if not (base and email and pw):
        return None, "base_url / email / password not set"
    data, err = _req("POST", f"{base}/api/auth/login", body={"email": email, "password": pw})
    if err:
        return None, f"login failed — {err}"
    tok = (data or {}).get("token")
    if not tok:
        return None, "login response had no token"
    _TOKEN_CACHE["token"] = tok
    _TOKEN_CACHE["exp"] = now + 6 * 86400
    return tok, None


def _scoped(cfg, path):
    base = (cfg.get("base_url") or "").rstrip("/")
    url = f"{base}{path}"
    tid = cfg.get("tenant_id")
    if tid:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"tenantId": tid})
    return url


def get_campaigns(cfg):
    """All campaigns with totals. Returns (list, error)."""
    tok, err = login(cfg)
    if err:
        return None, err
    data, err = _req("GET", _scoped(cfg, "/api/campaigns"), tok)
    if err:
        return None, err
    # API may return a bare list or {data:[...]} / {campaigns:[...]}.
    if isinstance(data, list):
        return data, None
    return data.get("data") or data.get("campaigns") or [], None


def get_campaign_stats(cfg, cid):
    """One campaign + stats (sent/delivered/read/failed/rates). Returns (dict, error)."""
    tok, err = login(cfg)
    if err:
        return None, err
    return _req("GET", _scoped(cfg, f"/api/campaigns/{cid}"), tok)


def campaign_funnels(cfg, limit=50):
    """Normalized funnel per campaign: name, sent, delivered, read, failed. Returns (list, error)."""
    camps, err = get_campaigns(cfg)
    if err:
        return None, err
    out = []
    for c in (camps or [])[:limit]:
        cid = c.get("id") or c.get("_id")
        s = c
        # If totals aren't on the list payload, fetch the detail.
        if not any(k in c for k in ("sent", "delivered", "read", "failed")):
            d, e = get_campaign_stats(cfg, cid)
            if not e and d:
                s = d.get("stats") or d.get("campaign") or d
        out.append({
            "id": cid,
            "name": c.get("name") or s.get("name") or str(cid),
            "status": c.get("status") or s.get("status"),
            "sent": int(s.get("sent", 0) or 0),
            "delivered": int(s.get("delivered", 0) or 0),
            "read": int(s.get("read", 0) or 0),
            "failed": int(s.get("failed", 0) or 0),
        })
    return out, None
