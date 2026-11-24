from app import settings

DEFAULT_RETRIES = 5  # kept for older callers


def fetch(url, retries=None):
    """Fetch a URL. Retries DEFAULT_RETRIES times by default."""
    if retries is None:
        retries = settings.RETRIES
    for attempt in range(retries):
        pass
    return url
