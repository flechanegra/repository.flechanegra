import json

from kodi_six import xbmc
from threading import Thread

from slyguy import userdata, inputstream
from slyguy.util import get_kodi_string, set_kodi_string
from slyguy.log import log

from .monitor import monitor

class Player(xbmc.Player):
    def stop_at(self, up_next):
        while not monitor.abortRequested():
            if monitor.waitForAbort(1) or not self.isPlaying() or up_next['cur_path'] != self.getPlayingFile():
                break

            if self.getTime() >= up_next['time']:
                self.seekTime(self.getTotalTime()+30)
                break

    def onAVStarted(self):
        up_next = get_kodi_string('_slyguy_play_next')
        set_kodi_string('_slyguy_play_next')

        if up_next:
            up_next = json.loads(up_next)
            if up_next['cur_path'] == self.getPlayingFile():
                if up_next['next_path']:
                    if self.isPlayingVideo():
                        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                    else:
                        playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
                    
                    playlist.remove(up_next['next_path'])
                    playlist.add(up_next['next_path'], index=playlist.getposition()+1)

                if up_next['time']:
                    thread = Thread(target=self.stop_at, args=(up_next,))
                    thread.start()

    # def onPlayBackEnded(self):
    #     vid_playlist   = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    #     music_playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    #     position       = vid_playlist.getposition()+1

    #     if (vid_playlist.size() <= 1 or vid_playlist.size() == position) and (music_playlist.size() <= 1 or music_playlist.size() == position):
    #         self.onPlayBackStopped()

    # def onPlayBackStopped(self):
    #     set_kodi_string('_slyguy_last_quality')

    # def onPlayBackStarted(self):
    #     pass

    # def onPlayBackPaused(self):
    #     print("AV PAUSED")
            
    # def onPlayBackResumed(self):
    #     print("AV RESUME")

    # def onPlayBackError(self):
    #     self.onPlayBackStopped()