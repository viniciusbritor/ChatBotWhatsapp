import json

new_webhook = "https://whatsapp-agente-test-894828119087.us-central1.run.app/webhook"

body = {
    "webhook": {
        "url": new_webhook,
        "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
        "enabled": True,
        "webhookByEvents": False,
        "webhookBase64": False,
    }
}

with open("C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime/webhook_body.json", "w") as f:
    json.dump(body, f)

print("Body salvo:", json.dumps(body, indent=2))
