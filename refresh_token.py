"""
Run this whenever you get 401 auth errors.
Silently refreshes token using saved refresh_token — no browser needed.
If refresh fails, falls back to full browser OAuth flow.
"""
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import json, os

TOKEN_FILE   = r"C:\Users\Asmita\documents\asmita\apps\chuk\ga4_token.json"
SECRETS_TOML = r"C:\Users\Asmita\documents\asmita\apps\chuk\ga4_live_brain\.streamlit\secrets.toml"
CLIENT_FILE  = r"C:\Users\Asmita\Downloads\client_secret_141789348200-2fa8mflp6ir0n1mbgbrrfqhaavoum3bg.apps.googleusercontent.com.json"
SCOPES       = ["https://www.googleapis.com/auth/analytics.readonly"]

def save(creds):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    t = json.loads(creds.to_json())
    os.makedirs(os.path.dirname(SECRETS_TOML), exist_ok=True)
    with open(SECRETS_TOML, "w") as f:
        f.write(f"""[ga4_token]
token = "{t.get('token','')}"
refresh_token = "{t.get('refresh_token','')}"
token_uri = "{t.get('token_uri','')}"
client_id = "{t.get('client_id','')}"
client_secret = "{t.get('client_secret','')}"
""")
    print("Token saved + secrets.toml updated")

with open(TOKEN_FILE) as f:
    t = json.load(f)

creds = Credentials(
    token=t["token"], refresh_token=t["refresh_token"],
    token_uri=t["token_uri"], client_id=t["client_id"], client_secret=t["client_secret"],
)

try:
    creds.refresh(Request())
    save(creds)
    print("Silent refresh OK — press R in Streamlit to reload")
except Exception as e:
    print(f"Silent refresh failed ({e}) — opening browser...")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    save(creds)
    print("Browser auth OK — press R in Streamlit to reload")
