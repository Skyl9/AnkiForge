import json

log_file = "/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/26bb7940-e793-4c2f-9ebf-05881a29b2e6/.system_generated/logs/transcript.jsonl"
old_js = ""
with open(log_file) as f:
    for line in f:
        try:
            data = json.loads(line)
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if tc["name"] == "replace_file_content" and "app.js" in tc["args"].get("TargetFile", ""):
                        old_content = tc["args"].get("TargetContent", "")
                        if "SLIM BAR NAVIGATION" in old_content:
                            old_js = old_content
        except Exception:
            pass
with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/maquette/concept_ide/app.js", encoding="utf-8") as f:
    current_js = f.read()

print("OLD JS (what was replaced when I added slim bar):")
print(old_js[:300] + "...")
print("\nCURRENT JS:")
print(current_js[:300] + "...")
