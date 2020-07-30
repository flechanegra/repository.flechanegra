
import glob
import os
import re
import traceback

import xbmc
import xbmcgui
import xbmcaddon

from resources.lib.modules import log_utils
from resources.lib.modules import control
from xbmc import (LOGDEBUG, LOGERROR, LOGFATAL, LOGINFO, LOGNONE, LOGNOTICE, LOGSEVERE, LOGWARNING)
import threading

control.execute('RunPlugin(plugin://%s)' % control.get_plugin_url({'action': 'service'}))

def syncTraktLibrary():
    control.execute(
        'RunPlugin(plugin://%s)' % 'plugin.video.marvelrus/?action=tvshowsToLibrarySilent&url=traktcollection')
    control.execute(
        'RunPlugin(plugin://%s)' % 'plugin.video.marvelrus/?action=moviesToLibrarySilent&url=traktcollection')

try:
    ModuleVersion = control.addon('script.module.marvelrus').getAddonInfo('version')
    AddonVersion = control.addon('plugin.video.marvelrus').getAddonInfo('version')
    RepoVersion = control.addon().getAddonInfo('version')

    log_utils.log('######################### Marvelrus ############################', log_utils.LOGNOTICE)
    log_utils.log('####### CURRENT Marvelrus VERSIONS REPORT ######################', log_utils.LOGNOTICE)
    log_utils.log('### Marvelrus PLUGIN VERSION: %s ###' % str(AddonVersion), log_utils.LOGNOTICE)
    log_utils.log('### Marvelrus SCRIPT VERSION: %s ###' % str(ModuleVersion), log_utils.LOGNOTICE)
    log_utils.log('### Marvelrus REPOSITORY VERSION: %s ###' % str(RepoVersion), log_utils.LOGNOTICE)
    log_utils.log('###############################################################', log_utils.LOGNOTICE)
except:
    log_utils.log('######################### Marvelrus ############################', log_utils.LOGNOTICE)
    log_utils.log('####### CURRENT Marvelrus VERSIONS REPORT ######################', log_utils.LOGNOTICE)
    log_utils.log('### ERROR GETTING Marvelrus VERSIONS - NO HELP WILL BE GIVEN AS THIS IS NOT AN OFFICIAL Marvelrus INSTALL. ###', log_utils.LOGNOTICE)
    log_utils.log('###############################################################', log_utils.LOGNOTICE)

if control.setting('autoTraktOnStart') == 'true':
    syncTraktLibrary()

if int(control.setting('schedTraktTime')) > 0:
    log_utils.log('###############################################################', log_utils.LOGNOTICE)
    log_utils.log('#################### STARTING TRAKT SCHEDULING ################', log_utils.LOGNOTICE)
    log_utils.log('#################### SCHEDULED TIME FRAME '+ control.setting('schedTraktTime')  + ' HOURS ################', log_utils.LOGNOTICE)
    timeout = 3600 * int(control.setting('schedTraktTime'))
    schedTrakt = threading.Timer(timeout, syncTraktLibrary)
    schedTrakt.start()

DEBUGPREFIX = '[COLOR blue][ Marvelrus DEBUG ][/COLOR]'


def log(msg, level=LOGNOTICE):

    try:
        if isinstance(msg, unicode):
            msg = '%s (ENCODED)' % (msg.encode('utf-8'))
        print('%s: %s' % (DEBUGPREFIX, msg))
    except Exception as e:
        try:
            xbmc.log('Logging Failure: %s' % (e), level)
        except Exception:
            pass


