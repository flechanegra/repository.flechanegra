# -*- coding: UTF-8 -*-
import xbmc, xbmcaddon, xbmcgui, xbmcplugin, os, sys, xbmcvfs, glob
import shutil, base64
import urllib2,urllib
import re
import time
from datetime import date, datetime, timedelta
try:    from sqlite3 import dbapi2 as database
except: from pysqlite2 import dbapi2 as database
from string import digits

ADDON_ID       = xbmcaddon.Addon().getAddonInfo('id')
ADDONTITLE     = '[COLOR red]Auto Cleaner[/COLOR]'
ADDON          = xbmcaddon.Addon(ADDON_ID)
HOME           = xbmc.translatePath('special://home/')
PLUGIN         = os.path.join(HOME,     'addons',    ADDON_ID)
LOG            = xbmc.translatePath('special://logpath/')
ADDONS         = os.path.join(HOME, 'addons')
USERDATA       = os.path.join(HOME, 'userdata')
ADDONDATA      = os.path.join(USERDATA, 'addon_data', ADDON_ID)
ICON           = os.path.join(PLUGIN, 'icon.png')
WIZLOG         = os.path.join(ADDONDATA, 'wizard.log')
DIALOG         = xbmcgui.Dialog()
dp             = xbmcgui.DialogProgress()

def getS(name):
	try: return ADDON.getSetting(name)
	except: return False


def log(log):
	xbmc.log("[%s]: %s" % (ADDONTITLE, log))
	if not os.path.exists(ADDONDATA): os.makedirs(ADDONDATA)
	if not os.path.exists(WIZLOG): f = open(WIZLOG, 'w'); f.close()
	with open(WIZLOG, 'r+') as f:
		line = "[%s %s] %s" % (datetime.now().date(), str(datetime.now().time())[:8], log)
		content = f.read()
		f.seek(0, 0)
		f.write(line.rstrip('\r\n') + '\n' + content)
		
def LogNotify(title,message,times=4000,icon=ICON):
	xbmc.executebuiltin('XBMC.Notification(%s, %s, %s, %s)' % (title , message , times, icon))
	
def killxbmc(over=False):
    if over: choice = 1						
    else: choice = DIALOG.yesno('[COLOR=green]Fechar o Kodi[/COLOR]', 'Prestes a fechar Kodi!', 'Quer continuar?', nolabel='No, Cancel',yeslabel='[COLOR=green]Yes, Close[/COLOR]')
    if choice == 1:
        myplatform = platform()
        ("Force Closing Kodi: Platform[%s]" % str(platform()), xbmc.LOGNOTICE)
        os._exit(1)

def platform():
	if xbmc.getCondVisibility('system.platform.android'):             return 'android'
	elif xbmc.getCondVisibility('system.platform.linux'):             return 'linux'
	elif xbmc.getCondVisibility('system.platform.linux.Raspberrypi'): return 'linux'
	elif xbmc.getCondVisibility('system.platform.windows'):           return 'windows'
	elif xbmc.getCondVisibility('system.platform.osx'):               return 'osx'
	elif xbmc.getCondVisibility('system.platform.atv2'):              return 'atv2'
	elif xbmc.getCondVisibility('system.platform.ios'):               return 'ios'
	elif xbmc.getCondVisibility('system.platform.darwin'):            return 'ios'
							
class cacheEntry:
    def __init__(self, namei):
        self.name = namei

def setupXvbmcEntries():
    pathName = 'special://home/addons/plugin.program.indigo'
    entries = 1             
    XvbmcEntries = []
    
    for x in range(entries):
        XvbmcEntries.append(cacheEntry(pathName[x]))
    
    return XvbmcEntries  

def clearCache():
    XvbmcEntries = setupXvbmcEntries() 
    for entry in XvbmcEntries:	
        lib = xbmc.translatePath(os.path.join('special://home/addons/plugin.program.indigo'))  		
        if os.path.exists(lib)==True:
            shutil.rmtree(lib)
            LogNotify(ADDONTITLE,'[COLOR yellow]Ficheiro foi apagado:[/COLOR] [COLOR green]Sucesso![/COLOR]')
            killxbmc(over=False)
        else: LogNotify(ADDONTITLE,'[COLOR white]Já não está no seu sistema![/COLOR]')	
    LogNotify(ADDONTITLE, 'Não tem ficheiro para ser eliminado!')	
clearCache()    