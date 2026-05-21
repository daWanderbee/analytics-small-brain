import os, urllib.request, json, shutil

VAULT = r"C:\Users\Asmita\Documents\Asmita\Obsidian\SEO"
PLUGINS_DIR = os.path.join(VAULT, ".obsidian", "plugins")

PLUGINS = {
    "dataview": {
        "repo": "blacksmithgu/obsidian-dataview",
        "files": ["main.js", "manifest.json", "styles.css"]
    },
    "obsidian-charts": {
        "repo": "phibr0/obsidian-charts",
        "files": ["main.js", "manifest.json", "styles.css"]
    },
    "templater-obsidian": {
        "repo": "SilentVoid13/Templater",
        "files": ["main.js", "manifest.json", "styles.css"]
    },
}

def download(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        return False

installed = []
for plugin_id, info in PLUGINS.items():
    plugin_dir = os.path.join(PLUGINS_DIR, plugin_id)
    os.makedirs(plugin_dir, exist_ok=True)
    print(f"\nInstalling {plugin_id}...")
    base_url = f"https://github.com/{info['repo']}/releases/latest/download"
    ok = False
    for fname in info["files"]:
        url = f"{base_url}/{fname}"
        dest = os.path.join(plugin_dir, fname)
        success = download(url, dest)
        status = "OK" if success else "skip"
        print(f"  {fname}: {status}")
        if fname == "main.js" and success:
            ok = True
    if ok:
        installed.append(plugin_id)
        print(f"  -> {plugin_id} installed")
    else:
        print(f"  -> {plugin_id} FAILED")

# Enable plugins in community-plugins.json
cp_path = os.path.join(VAULT, ".obsidian", "community-plugins.json")
existing = []
if os.path.exists(cp_path):
    with open(cp_path) as f:
        existing = json.load(f)

merged = list(set(existing + installed))
with open(cp_path, "w") as f:
    json.dump(merged, f, indent=2)

print(f"\nEnabled plugins: {merged}")
print("\nDone. Restart Obsidian to activate.")
