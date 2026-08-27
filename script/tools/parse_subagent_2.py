import json

log_file = "/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/e9bcbf4c-bbd5-4092-bd7d-6a6d9b8f07fe/.system_generated/logs/transcript.jsonl"
writes = []
with open(log_file, "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if tc["name"] == "write_to_file" and "app.js" in tc["args"].get("TargetFile", ""):
                        writes.append(tc["args"].get("CodeContent"))
        except:
            pass

print(writes[-1] if writes else "No writes found")
