"""Pipelines independentes para roteamento de intents no WhatsApp.

Cada pipeline tem:
- detect(text) -> bool
- run(payload) -> dict

Módulos de infra compartilhados (_guard, _prefetch, _ack, _executor)
são importados apenas pelos pipelines que precisam deles.
"""
