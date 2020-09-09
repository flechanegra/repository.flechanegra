import time
from threading import Thread
from six.moves.urllib_parse import urlparse

from kodi_six import xbmc

from . import userdata, gui, router, inputstream, settings
from .session import Session
from .language import _
from .constants import QUALITY_TYPES, QUALITY_ASK, QUALITY_BEST, QUALITY_CUSTOM, QUALITY_SKIP, QUALITY_LOWEST, QUALITY_TAG, QUALITY_DISABLED, ADDON_DEV, COMMON_ADDON, ADDON_ID
from .log import log
from .parser import M3U8, MPD, ParserError
from .exceptions import FailedPlayback
from .util import get_kodi_setting, set_kodi_setting, hash_6, get_kodi_string, set_kodi_string

common_data = userdata.Userdata(COMMON_ADDON)

def select_quality(qualities, allow_skip=True):
    options = []

    options.append([QUALITY_BEST, _.QUALITY_BEST])
    options.extend(qualities)
    options.append([QUALITY_LOWEST, _.QUALITY_LOWEST])

    if allow_skip:
        options.append([QUALITY_SKIP, _.QUALITY_SKIP])

    values = [x[0] for x in options]
    labels = [x[1] for x in options]

    current = userdata.get('last_quality')

    default = -1
    if current:
        try:
            default = values.index(current)
        except:
            default = values.index(qualities[-1][0])

            for quality in qualities:
                if quality[0] <= current:
                    default = values.index(quality[0])
                    break

    index = gui.select(_.PLAYBACK_QUALITY, labels, preselect=default, autoclose=10000) #autoclose after 10seconds
    if index < 0:
        raise FailedPlayback('User cancelled quality select')

    userdata.set('last_quality', values[index])

    return values[index]

def reset_thread(_id):
    log.debug('Settings Reset Thread: STARTED')

    if ADDON_DEV:
        return

    monitor    = xbmc.Monitor()
    player     = xbmc.Player()
    sleep_time = 100#ms

    # wait upto 10 seconds for playback to start
    count = 0
    while not monitor.abortRequested():
        if player.isPlaying():
            break

        if count > 10*(1000/sleep_time):
            break

        count += 1
        xbmc.sleep(sleep_time)

    # wait until playback stops
    while not monitor.abortRequested():
        if not player.isPlaying():
            break
        
        xbmc.sleep(sleep_time)

    reset_settings = common_data.get('reset_settings')
    if reset_settings and reset_settings[0] == _id:
        if reset_settings[1]:
            inputstream.set_settings(reset_settings[2])
        else:
            set_gui_settings(reset_settings[2])

        common_data.delete('reset_settings')

    log.debug('Reset Settings Thread: DONE')

def set_settings(min_bandwidth, max_bandwidth, is_ia=False):
    if is_ia:
        new_settings = {
            'MINBANDWIDTH':        min_bandwidth,
            'MAXBANDWIDTH':        max_bandwidth,
            'IGNOREDISPLAY':       'true',
            'HDCPOVERRIDE':        'true',
            'STREAMSELECTION':     '0',
            'MAXRESOLUTION':       '0',
            'MAXRESOLUTIONSECURE': '0',
            #'MEDIATYPE':           '0',
        }

        inputstream.set_bandwidth_bin(1000000000) #1000m/bit

        old_settings = inputstream.get_settings(new_settings.keys())
        inputstream.set_settings(new_settings)
    else:
        new_settings = {
            'network.bandwidth': int(max_bandwidth/1000),
        }

        old_settings = get_gui_settings(new_settings.keys())
        set_gui_settings(new_settings)

    _id = time.time()
    settings = common_data.get('reset_settings', [_id, is_ia, old_settings])
    common_data.set('reset_settings', settings)
    
    thread = Thread(target=reset_thread, args=(_id,))
    thread.start()

def get_gui_settings(keys):
    settings = {}

    for key in keys:
        settings[key] = get_kodi_setting(key)
        
    return settings

def set_gui_settings(settings):
    for key in settings:
        set_kodi_setting(key, settings[key])

def get_quality():
    return settings.getEnum('default_quality', QUALITY_TYPES, default=QUALITY_ASK)

def add_context(item):
    _quality = get_quality()
    if item.path and item.playable and _quality not in (QUALITY_DISABLED, QUALITY_ASK):
        url = router.add_url_args(item.path, **{QUALITY_TAG: QUALITY_ASK})
        item.context.append((_.PLAYBACK_QUALITY, 'PlayMedia({},noresume)'.format(url)))

def parse(item, quality=None):
    if quality is None:
        quality = get_quality()
        if quality == QUALITY_CUSTOM:
            quality = int(settings.getFloat('max_bandwidth')*1000000)
    else:
        quality = int(quality)

    if quality in (QUALITY_DISABLED, QUALITY_SKIP):
        return

    url   = item.path.split('|')[0]
    parse = urlparse(url.lower())
    
    if 'http' not in parse.scheme:
        return

    parser = None
    if item.inputstream and item.inputstream.check():
        is_ia = True
        if item.inputstream.manifest_type == 'mpd':
            parser = MPD()
        elif item.inputstream.manifest_type == 'hls':
            parser = M3U8()
    else:
        is_ia = False
        if parse.path.endswith('.m3u') or parse.path.endswith('.m3u8'):
            parser = M3U8()

    if not parser:
        return

    if item.use_proxy:
        url = gui.PROXY_PATH + url

    try:
        resp = Session().get(url, headers=item.headers, cookies=item.cookies, attempts=1)
    except Exception as e:
        log.exception(e)
        return False
    else:
        result = resp.ok

    if not result:
        gui.ok(_(_.QUALITY_PARSE_ERROR, error=_(_.QUALITY_HTTP_ERROR, code=resp.status_code)))
        return False

    try:
        parser.parse(resp.text)
        qualities = parser.qualities()
    except Exception as e:
        log.exception(e)
        gui.ok(_(_.QUALITY_PARSE_ERROR, error=e))
        return

    if len(qualities) < 2:
        log.debug('Only found {} quality, skipping quality select'.format(len(qualities)))
        return

    qualities = sorted(qualities, key=lambda s: s[0], reverse=True)

    if quality == QUALITY_ASK:
        quality      = get_kodi_string('_slyguy_last_quality')
        addon        = get_kodi_string('_slyguy_last_addon')
        playlist_pos = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()

        # if quality and (addon == ADDON_ID or xbmc.getCondVisibility('Pvr.IsPlayingTv')) and (playlist_pos > 0 or (xbmc.Player().isPlaying() and playlist_pos == -1)):
        #     quality = int(quality)
        # else:
        quality = select_quality(qualities)

        set_kodi_string('_slyguy_last_quality', quality)
        set_kodi_string('_slyguy_last_addon', ADDON_ID)

        if quality == QUALITY_SKIP:
            return

    if quality == QUALITY_BEST:
        quality = qualities[0][0]
    elif quality == QUALITY_LOWEST:
        quality = qualities[-1][0]

    min_bandwidth, max_bandwidth = parser.bandwidth_range(quality)
    set_settings(min_bandwidth, max_bandwidth, is_ia)