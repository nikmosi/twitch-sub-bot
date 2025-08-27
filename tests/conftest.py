import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    os.environ["TWITCH_CLIENT_ID"] = "pytest_TWITCH_CLIENT_ID"
    os.environ["TWITCH_CLIENT_SECRET"] = "pytest_TWITCH_CLIENT_SECRET"
    os.environ["TELEGRAM_BOT_TOKEN"] = "pytest_TELEGRAM_BOT_TOKEN"
    os.environ["TELEGRAM_CHAT_ID"] = "pytest_TELEGRAM_CHAT_ID"

    yield
