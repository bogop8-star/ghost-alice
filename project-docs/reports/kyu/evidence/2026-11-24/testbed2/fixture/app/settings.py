import os

RETRIES = int(os.environ.get("APP_RETRIES", "7"))
