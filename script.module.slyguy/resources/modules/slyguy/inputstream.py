import os
import platform
import re
import shutil
import time
import struct
from distutils.version import LooseVersion

from kodi_six import xbmc, xbmcaddon

from . import gui, settings
from .userdata import Userdata
from .session import Session
from .log import log
from .constants import IA_ADDON_ID, IA_TESTING_ID, IA_VERSION_KEY, IA_HLS_MIN_VER, IA_MPD_MIN_VER, IA_MODULES_URL, IA_CHECK_EVERY, COMMON_ADDON, KODI_VERSION
from .language import _
from .util import md5sum, remove_file, get_system_arch, hash_6, kodi_rpc, get_addon
from .exceptions import InputStreamError

ADDON_ID = IA_ADDON_ID

def get_id():
    if ADDON_ID == IA_ADDON_ID:
        try:
            xbmcaddon.Addon(IA_TESTING_ID)
            return IA_TESTING_ID
        except: pass

    return ADDON_ID

def get_ia_addon(required=False, install=True):
    return get_addon(get_id(), required=required, install=install)

class InputstreamItem(object):
    manifest_type = ''
    license_type  = ''
    license_key   = ''
    mimetype      = ''
    checked       = None
    license_data  = None
    challenge     = None
    response      = None
    properties    = None

    def __init__(self, properties=None):
        self.properties = properties or {}

    @property
    def addon_id(self):
        return get_id()

    def do_check(self):
        return False

    def check(self):
        if self.checked is None:
            self.checked = self.do_check()
            
        return self.checked

class HLS(InputstreamItem):
    manifest_type = 'hls'
    mimetype      = 'application/vnd.apple.mpegurl'

    def __init__(self, force=False, live=True, **kwargs):
        super(HLS, self).__init__(**kwargs)
        self.force = force
        self.live  = live

    def do_check(self):
        legacy   = settings.getBool('use_ia_hls', False)
        hls_live = settings.getBool('use_ia_hls_live', legacy)
        hls_vod  = settings.getBool('use_ia_hls_vod', legacy)

        return (self.force or (self.live and hls_live) or (not self.live and hls_vod)) and supports_hls(required=self.force)
        
class MPD(InputstreamItem):
    manifest_type = 'mpd'
    mimetype      = 'application/dash+xml'

    def do_check(self):
        return supports_mpd()

class Playready(InputstreamItem):
    manifest_type = 'ism'
    license_type  = 'com.microsoft.playready'
    mimetype      = 'application/vnd.ms-sstr+xml'

    def do_check(self):
        return supports_playready()

class Widevine(InputstreamItem):
    license_type  = 'com.widevine.alpha'

    def __init__(self, license_key=None, content_type='application/octet-stream', challenge='R{SSM}', response='', manifest_type='mpd', mimetype='application/dash+xml', license_data=None, **kwargs):
        super(Widevine, self).__init__(**kwargs)
        self.license_key   = license_key
        self.content_type  = content_type
        self.challenge     = challenge
        self.response      = response
        self.manifest_type = manifest_type
        self.mimetype      = mimetype
        self.license_data  = license_data

    def do_check(self):
        return install_widevine()

def set_bandwidth_bin(bps):
    addon = get_ia_addon(install=False)
    if not addon:
        return

    addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
    bin_path = os.path.join(addon_profile, 'bandwidth.bin')

    if not os.path.exists(addon_profile):
        os.makedirs(addon_profile)

    value = bps / 8
    with open(bin_path, 'wb') as f:
        f.write(struct.pack('d', value))

    log.debug('IA Set Bandwidth Bin: {} bps'.format(bps))

def set_settings(settings):
    addon = get_ia_addon(install=False)
    if not addon:
        return

    log.debug('IA Set Settings: {}'.format(settings))

    for key in settings:
        addon.setSetting(key, str(settings[key]))

def get_settings(keys):
    addon = get_ia_addon(install=False)
    if not addon:
        return None

    settings = {}
    for key in keys:
        settings[key] = addon.getSetting(key)

    return settings

def open_settings():
    ia_addon = get_ia_addon()
    if ia_addon:
        ia_addon.openSettings()

def require_version(required_version, required=False):
    ia_addon = get_ia_addon(required=required)    
    if not ia_addon:
        return False

    return LooseVersion(ia_addon.getAddonInfo('version')) >= LooseVersion(required_version)

def supports_hls(required=False):
    return require_version(IA_HLS_MIN_VER, required=required)

def supports_mpd(required=False):
    return require_version(IA_MPD_MIN_VER, required=required)

def supports_playready():
    return bool(get_ia_addon() and KODI_VERSION > 17 and xbmc.getCondVisibility('system.platform.android'))

def install_widevine(reinstall=False):
    system, arch = get_system_arch()

    if KODI_VERSION < 18:
        raise InputStreamError(_(_.IA_KODI18_REQUIRED, system=system))

    ia_addon = get_ia_addon(required=True)

    DST_FILES = {
        'Linux':   'libwidevinecdm.so',
        'Darwin':  'libwidevinecdm.dylib',
        'Windows': 'widevinecdm.dll',
    }

    if system == 'Android':
        return True

    elif system == 'UWP':
        raise InputStreamError(_.IA_UWP_ERROR)

    elif 'aarch64' in arch or 'arm64' in arch:
        raise InputStreamError(_.IA_AARCH64_ERROR)
    
    elif system not in DST_FILES:
        raise InputStreamError(_(_.IA_NOT_SUPPORTED, system=system, arch=arch, kodi_version=KODI_VERSION))

    userdata     = Userdata(COMMON_ADDON)
    decryptpath  = xbmc.translatePath(ia_addon.getSetting('DECRYPTERPATH'))
    wv_path      = os.path.join(decryptpath, DST_FILES[system])
    installed    = md5sum(wv_path)
    last_check   = int(userdata.get('_wv_last_check', 0))

    if not installed:
        reinstall = True

    if not reinstall and time.time() - last_check < IA_CHECK_EVERY:
        return True

    ## DO INSTALL ##
    userdata.set('_wv_last_check', int(time.time()))

    r = Session().get(IA_MODULES_URL)
    if r.status_code != 200:
        raise InputStreamError(_(_.ERROR_DOWNLOADING_FILE, filename=IA_MODULES_URL.split('/')[-1]))

    widevine     = r.json()['widevine']
    wv_versions  = widevine['platforms'].get(system + arch, [])
    latest       = wv_versions[0]
    latest_known = userdata.get('_wv_latest_md5')
    userdata.set('_wv_latest_md5', latest['md5'])

    if not wv_versions:
        raise InputStreamError(_(_.IA_NOT_SUPPORTED, system=system, arch=arch, kodi_version=KODI_VERSION))

    if not reinstall and (installed == latest['md5'] or latest['md5'] == latest_known):
        return True

    current = None
    for wv in wv_versions:
        if wv['md5'] == installed:
            current = wv
            wv['label'] = _(_.WV_INSTALLED, version=wv['ver'])
        else:
            wv['label'] = wv['ver']

    if installed and not current:
        wv_versions.append({
            'ver': installed[:6],
            'label': _(_.WV_UNKNOWN, version=installed[:6]),
        })

    latest['label'] = _(_.WV_LATEST, label=latest['label'])
    labels = [x['label'] for x in wv_versions]

    index = gui.select(_.SELECT_WV_VERSION, options=labels)
    if index < 0:
        return False

    selected = wv_versions[index]

    if 'src' in selected:
        url = widevine['base_url'] + selected['src']
        if not _download(url, wv_path, selected['md5']):
            return False

    if selected != latest:
        message = _.WV_NOT_LATEST
    else:
        message = _.IA_WV_INSTALL_OK
    
    gui.ok(_(message, version=selected['ver']))

    return True

def _download(url, dst_path, md5=None):
    dir_path = os.path.dirname(dst_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    filename   = url.split('/')[-1]
    downloaded = 0

    if os.path.exists(dst_path):
        if md5 and md5sum(dst_path) == md5:
            log.debug('MD5 of local file {} same. Skipping download'.format(filename))
            return True
        else:
            remove_file(dst_path)
            
    with gui.progress(_(_.IA_DOWNLOADING_FILE, url=filename), heading=_.IA_WIDEVINE_DRM) as progress:
        resp = Session().get(url, stream=True)
        if resp.status_code != 200:
            raise InputStreamError(_(_.ERROR_DOWNLOADING_FILE, filename=filename))

        total_length = float(resp.headers.get('content-length', 1))

        with open(dst_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=settings.getInt('chunksize', 4096)):
                f.write(chunk)
                downloaded += len(chunk)
                percent = int(downloaded*100/total_length)

                if progress.iscanceled():
                    progress.close()
                    resp.close()

                progress.update(percent)

    if progress.iscanceled():
        remove_file(dst_path)            
        return False

    checksum = md5sum(dst_path)
    if checksum != md5:
        remove_file(dst_path)
        raise InputStreamError(_(_.MD5_MISMATCH, filename=filename, local_md5=checksum, remote_md5=md5))
    
    return True