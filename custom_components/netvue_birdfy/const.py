"""Constants for the Netvue Birdfy integration."""
from datetime import timedelta

DOMAIN = "netvue_birdfy"

CONF_PASSWORD_MD5 = "password_md5"
CONF_UDID = "udid"
CONF_USERID = "userid"

SCAN_INTERVAL = timedelta(minutes=5)
# Download links stay valid for 3 days; look back that far on every poll so a
# missed or failed download is retried.
LOOKBACK = timedelta(days=3)
LINK_BATCH = 20

EVENT_VISIT = "visit"
