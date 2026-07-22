import datetime


def get_ist_time() -> datetime.datetime:
    """
    Returns current timezone-naive datetime representing Indian Standard Time (UTC+5:30).
    Allows uniform timestamp tracking across host servers (e.g. Render, AWS, Heroku)
    independent of the host server location.
    """
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).replace(tzinfo=None)
