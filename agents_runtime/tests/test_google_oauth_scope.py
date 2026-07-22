from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "tools.google_calendar",
        "tools.google_drive",
        "tools.google_gmail",
    ],
)
def test_user_scoped_google_credentials_fail_closed(module_name):
    module = __import__(module_name, fromlist=["_get_credentials"])
    with patch("core.oauth_per_user.get_user_credentials", return_value=None):
        with patch("core.secrets.get_secret") as global_secret:
            with pytest.raises(RuntimeError, match="user_google_oauth_required"):
                module._get_credentials("5511966830020")
    global_secret.assert_not_called()
