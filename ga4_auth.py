from google_auth_oauthlib.flow import InstalledAppFlow
from google.analytics.admin import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import ListPropertiesRequest
import json

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics",
]

CLIENT_SECRETS = r"C:\Users\Asmita\Downloads\client_secret_141789348200-2fa8mflp6ir0n1mbgbrrfqhaavoum3bg.apps.googleusercontent.com.json"
TOKEN_FILE = "ga4_token.json"

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())
print(f"Token saved to {TOKEN_FILE}")

client = AnalyticsAdminServiceClient(credentials=creds)

print("\n=== ACCOUNTS ===")
accounts = list(client.list_accounts())
if not accounts:
    print("  (none)")
for acc in accounts:
    print(f"  {acc.name} | {acc.display_name}")

    print(f"\n  === PROPERTIES under {acc.display_name} ===")
    req = ListPropertiesRequest(filter=f"parent:{acc.name}", show_deleted=False)
    props = list(client.list_properties(request=req))
    if not props:
        print("    (none)")
    for prop in props:
        print(f"    {prop.name} | {prop.display_name} | {prop.time_zone}")
