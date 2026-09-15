import json

log_file = "/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/26bb7940-e793-4c2f-9ebf-05881a29b2e6/.system_generated/logs/transcript.jsonl"
with open(log_file, "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if tc["name"] == "write_to_file" and "app.js" in tc["args"].get("TargetFile", ""):
                        if "concept_ide" in tc["args"].get("TargetFile", ""):
                            print("---- WRITE TO FILE ----")
                            print(tc["args"].get("CodeContent"))
                            print("----------------------")
        except:
            pass
