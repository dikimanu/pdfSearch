import json, urllib.request, urllib.error
import core

s = core.load_settings()
key = s.get("gemini_api_key", "").strip()
print("Model saved in Settings:", repr(s.get("model")))
if not key:
    raise SystemExit("No key saved in the app's Settings.")

req = urllib.request.Request(core.BASE, headers={"x-goog-api-key": key})
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.load(r)
print("\nModels your key can use for answers:")
for m in data.get("models", []):
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print("  ", m["name"].replace("models/", ""))

print("\nTesting the names the app uses:")
for name in ["gemini-flash-lite-latest", s.get("model"), "gemini-2.5-flash"]:
    out = core.ask_gemini("Reply with the single word OK.", timeout=40, models=[name])
    print("  %-28s %s" % (name, "works" if out else "FAILED: " + core.AI_STATE["error"]))