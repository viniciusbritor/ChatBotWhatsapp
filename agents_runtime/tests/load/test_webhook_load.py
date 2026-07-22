import os


if os.getenv("RUN_LOAD_TEST") == "1":
    from locust import FastHttpUser, between, task


    class WebhookLoadUser(FastHttpUser):
        host = os.getenv("LOAD_TEST_BASE_URL", "http://localhost:8080")
        wait_time = between(0.5, 1.5)

        @task
        def send_webhook(self):
            message_id = f"LOAD-{self.environment.runner.stats.total.num_requests}"
            self.client.post(
                "/webhook",
                json={
                    "event": "MESSAGES_UPSERT",
                    "instance": "jennifer-load",
                    "data": {
                        "key": {
                            "remoteJid": "0000000000000@s.whatsapp.net",
                            "fromMe": False,
                            "id": message_id,
                        },
                        "pushName": "Load Test",
                        "message": {"conversation": "mensagem de carga"},
                        "messageType": "conversation",
                    },
                },
                name="POST /webhook",
            )
