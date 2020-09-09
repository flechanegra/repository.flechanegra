import os

from slyguy.constants import ADDON_PROFILE

## PROXY ##
PROXY_PORT         = 52530
PROXY_CACHE        = os.path.join(ADDON_PROFILE, 'proxy_cache')
PROXY_CACHE_AHEAD  = 0
PROXY_CACHE_BEHIND = 0

## NEWS ##
NEWS_URL           = 'https://k.slyguy.xyz/.repo/news.json'
ADDONS_URL         = 'https://k.slyguy.xyz/.repo/addons.json'
ADDONS_MD5         = 'https://k.slyguy.xyz/.repo/addons.xml.md5'
NEWS_CHECK_TIME    = 7200 #2 Hours
UPDATES_CHECK_TIME = 3600 #1 Hour
NEWS_MAX_TIME      = 432000 #5 Days
SERVICE_BUILD_TIME = 3600 #1 Hour