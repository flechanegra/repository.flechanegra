import re
from xml.dom.minidom import parseString

from . import gui
from .language import _
from .util import strip_namespaces
from .constants import KODI_VERSION

class ParserError(Exception):
    pass

class Parser(object):
    def __init__(self):
        self._streams = []

    def parse(self, text):
        raise Exception('Not implemented')

    def streams(self):
        return sorted(self._streams, key=lambda s: s['bandwidth'], reverse=True)

    def qualities(self):
        qualities  = []
        bandwidths = []

        for stream in self.streams():
            if stream['bandwidth'] in bandwidths:
                continue

            bandwidths.append(stream['bandwidth'])

            try:
                fps = _(_.QUALITY_FPS, fps=float(stream['frame_rate']))
            except:
                fps = ''

            qualities.append([stream['bandwidth'], _(_.QUALITY_BITRATE, bandwidth=float(stream['bandwidth'])/1000000, resolution=stream['resolution'], fps=fps)])

        return qualities

    def bandwidth_range(self, quality):
        qualities = []
        for stream in self.streams():
            if stream['bandwidth'] not in qualities:
                qualities.append(stream['bandwidth'])

        selected = qualities[-1]

        for bandwidth in qualities:
            if bandwidth <= quality:
                selected = bandwidth
                break

        qualities.insert(0, 1)
        qualities.append(0)

        index = qualities.index(selected)

        return qualities[index+1]+1, qualities[index-1]-1

class M3U8(Parser):
    def parse(self, text):
        if not text.upper().startswith('#EXTM3U'):
            raise ParserError(_.QUALITY_BAD_M3U8)

        marker = '#EXT-X-STREAM-INF:'
        pattern = re.compile(r'''((?:[^,"']|"[^"]*"|'[^']*')+)''')

        line1 = None
        for line in text.split('\n'):
            line = line.strip()

            if not line:
                continue

            if line.startswith(marker):
                line1 = line
            elif line1 and not line.startswith('#'):
                params = pattern.split(line1.replace(marker, ''))[1::2]

                attributes = {}
                for param in params:
                    name, value = param.split('=', 1)
                    name  = name.replace('-', '_').lower().strip()
                    value = value.lstrip('"').rstrip('"')

                    attributes[name] = value

                num_codecs = 0
                if 'codecs' in attributes:
                    num_codecs = len(attributes['codecs'].split(','))

                bandwidth  = attributes.get('bandwidth')
                resolution = attributes.get('resolution', '')
                frame_rate = attributes.get('frame_rate', '')

                if bandwidth and (num_codecs != 1 or resolution or frame_rate):
                    self._streams.append({'bandwidth': int(bandwidth), 'resolution': resolution, 'frame_rate': frame_rate})

                line1 = None

class MPD(Parser):
    def parse(self, text):
        root = parseString(text)
        mpd  = root.getElementsByTagName("MPD")[0]

        num_baseurls = 0
        for node in mpd.childNodes:
            if node.nodeType == node.ELEMENT_NODE:
                if node.localName == 'BaseURL':
                    num_baseurls += 1

        if num_baseurls > 1 and KODI_VERSION < 19:
            gui.ok(_.MULTI_BASEURL_WARNING)

        all_streams = []
        for adap_set in root.getElementsByTagName('AdaptationSet'):
            streams = []

            for stream in adap_set.getElementsByTagName("Representation"):
                attrib = {}
                for key in adap_set.attributes.keys():
                    attrib[key] = adap_set.getAttribute(key)

                for key in stream.attributes.keys():
                    attrib[key] = stream.getAttribute(key)

                if 'video' in attrib.get('mimeType', '') and 'bandwidth' in attrib:
                    bandwidth = int(attrib['bandwidth'])

                    resolution = ''
                    if 'width' in attrib and 'height' in attrib:
                        resolution = '{}x{}'.format(attrib['width'], attrib['height'])

                    frame_rate = ''
                    if 'frameRate'in attrib:
                        frame_rate = attrib['frameRate']
                        try:
                            if '/' in str(frame_rate):
                                split = frame_rate.split('/')
                                frame_rate = float(split[0]) / float(split[1])
                        except:
                            frame_rate = ''

                    streams.append({'bandwidth': bandwidth, 'resolution': resolution, 'frame_rate': frame_rate})

            if streams:
                all_streams.append(streams)

        ## IA  only selects video streams from 1st adaption set
        if all_streams:
            self._streams = all_streams[0]