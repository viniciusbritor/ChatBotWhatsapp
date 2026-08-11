"""Shared Composio config — toolkit versions pinned for all apps.

NOTA (10/08/2026): Gmail, Calendar e Drive NAO usam Composio — usam OAuth
direto (core.oauth_per_user + googleapiclient) com token em
usuarios/{phone}.google_oauth_token. Google Maps tambem e API direta
(tools/transporte.py, google-maps-api-key). Por isso os pins destes
toolkits foram removidos.
"""
TOOLKIT_VERSIONS = {
    "youtube": "20260721_00",
    "linkedin": "20260724_00",
    "googledocs": "20260721_00",
    "github": "20260728_00",
    "notion": "20260730_00",
    "googlesheets": "20260806_00",
    "one_drive": "20260804_00",
}
