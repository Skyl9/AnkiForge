import json

log_file = "/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/26bb7940-e793-4c2f-9ebf-05881a29b2e6/.system_generated/logs/transcript.jsonl"
with open(log_file, "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if tc["name"] == "replace_file_content" and "app.js" in tc["args"].get("TargetFile", ""):
                        old = tc["args"].get("TargetContent", "")
                        if "SLIM BAR NAVIGATION" in old:
                            print("FOUND SLIM BAR REPLACE")
                            print(old)
        except:
            pass
