import threading
import os
import shutil
import re
import uuid

from io import BytesIO, SEEK_END
from xml.dom.minidom import parseString
from collections import defaultdict, OrderedDict

from six.moves.BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from six.moves.socketserver import ThreadingMixIn
from six.moves.urllib.parse import urlparse, urljoin, unquote, parse_qsl
from kodi_six import xbmc, xbmcvfs
from requests import Session

from slyguy.log import log
from slyguy.constants import ADDON_DEV
from slyguy import settings

from .constants import PROXY_CACHE, PROXY_CACHE_AHEAD, PROXY_CACHE_BEHIND

patterns = {}
sessions = OrderedDict()

REMOVE_IN_HEADERS  = ['_proxy_default_language', '_quality']
REMOVE_OUT_HEADERS = ['connection', 'transfer-encoding', 'content-encoding', 'date', 'server', 'content-length', '_orig_location']

HOST = settings.get('proxy_host')
PORT = settings.getInt('proxy_port')
PROXY_PATH = 'http://{}:{}/'.format(HOST, PORT)

def devlog(msg):
    if ADDON_DEV:
        log.debug(msg)

class ResponseStream(object):
    def __init__(self, response, chunk_size=None):
        self._bytes = BytesIO()
        self._response = response
        self._iterator = response.iter_content(chunk_size)
        self._chunk_size = chunk_size

    def _load_until(self, goal_position=None):
        current_position = self._bytes.seek(0, SEEK_END)

        while goal_position is None or current_position < goal_position:
            try:
                current_position = self._bytes.write(next(self._iterator))
            except StopIteration:
                break

    @property
    def size(self):
        return self._size

    def tell(self):
        return self._bytes.tell()

    def read(self, size=None, start_from=None):
        if size is None:
            left_off_at = start_from or 0
            goal_position = None
        else:
            left_off_at = start_from or self._bytes.tell()
            goal_position = left_off_at + size
        
        self._load_until(goal_position)
        self._bytes.seek(left_off_at)

        return self._bytes.read(size)

    def set(self, _bytes):
        self._bytes = BytesIO(_bytes)

    def iter_content(self):
        self._bytes.seek(0)

        while True:
            chunk = self._bytes.read(self._chunk_size)
            if not chunk:
                break

            yield chunk
            
        for chunk in self._iterator:
            yield chunk

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self._chunk_size = 4096
        self._override_headers = {}
        BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    def log_message(self, format, *args):
        return

    def setup(self):
        BaseHTTPRequestHandler.setup(self)
        self.request.settimeout(5)

    def _plugin_request(self, url):
        dirs, files = xbmcvfs.listdir(url)

        path = unquote(files[0])
        split = path.split('|')
        url = split[0]

        if len(split) > 1:
            self._override_headers = dict(parse_qsl(u'{}'.format(split[1]), keep_blank_values=True))

        return url

    def _get_url(self):
        url = self.path.lstrip('/').strip('\\')

        if url.lower().startswith('plugin'):
            url = self._plugin_request(url)

        return url

    def do_GET(self):
        url = self._get_url()
        devlog('GET IN: {}'.format(url))

        response = self._proxy_request('GET', url)
        if not response.ok:
            self._output_response(response)
            return

        first_chunk = response.stream.read(self._chunk_size, start_from=0)

        if b'urn:mpeg:dash:schema' in first_chunk.lower():
            self._parse_dash(response)

        elif b'#extm3u' in first_chunk.lower():
            self._parse_m3u8(response)

        self._output_response(response)
                        
    def _parse_dash(self, response):
        try:
            root = parseString(response.stream.read())
        except:
            log.debug("Failed to parse MPD")
            return self._output_response(response)

        mpd = root.getElementsByTagName("MPD")[0]

        # if response.url not in patterns:
        #     patterns[response.url] = {}

        base_urls      = []
        base_url_nodes = []

        for node in mpd.childNodes:
            if node.nodeType == node.ELEMENT_NODE:
                if node.localName == 'BaseURL':
                    url = node.firstChild.nodeValue

                    if not url.startswith('http'):
                        url = urljoin(response.url, url)

                    base_urls.append(url)
                    base_url_nodes.append(node)
                    node.firstChild.nodeValue = PROXY_PATH + url

        if not base_urls:
            base_urls = [response.url]

        ### SKY GO FIX
        ## FIXED WITH COMMIT: https://github.com/peak3d/inputstream.adaptive/commit/dc7b42783d18c65ebcf205a4979a1c9ea6b825e7
        if 'availabilityStartTime' in mpd.attributes.keys():
            mpd.removeAttribute('availabilityStartTime')
        ##############

        # Keep first base_url node
        if base_url_nodes:
            base_url_nodes.pop(0)
            for e in base_url_nodes:
                mpd.removeChild(e)
        ####################

        ## SUPPORT NEW DOLBY FORMAT
        ## PR to fix in IA: https://github.com/peak3d/inputstream.adaptive/pull/466
        for elem in root.getElementsByTagName('AudioChannelConfiguration'):
            if elem.getAttribute('schemeIdUri') == 'tag:dolby.com,2014:dash:audio_channel_configuration:2011':
                elem.setAttribute('schemeIdUri', 'urn:dolby:dash:audio_channel_configuration:2011')
        ###########################

        ## SORT ADAPTION SETS BY BITRATE ##
        video_sets = []
        audio_sets = []

        for adap_set in root.getElementsByTagName('AdaptationSet'):
            highest_bandwidth = 0
            is_video = False

            for stream in adap_set.getElementsByTagName("Representation"):
                attrib = {}

                for key in adap_set.attributes.keys():
                    attrib[key] = adap_set.getAttribute(key)

                for key in stream.attributes.keys():
                    attrib[key] = stream.getAttribute(key)

                if 'bandwidth' in attrib:
                    bandwidth = int(attrib['bandwidth'])
                    if bandwidth > highest_bandwidth:
                        highest_bandwidth = bandwidth
                
                if 'video' in attrib.get('mimeType', ''):
                    is_video = True

            parent = adap_set.parentNode
            parent.removeChild(adap_set)

            if is_video:
                video_sets.append([highest_bandwidth, adap_set, parent])
            else:
                audio_sets.append([highest_bandwidth, adap_set, parent])

        for elem in sorted(video_sets, key=lambda  x: x[0], reverse=True):
            elem[2].appendChild(elem[1])

        for elem in sorted(audio_sets, key=lambda  x: x[0], reverse=True):
            elem[2].appendChild(elem[1])

        devlog("Adaption Sets Sorted")
        ##################

        elems = root.getElementsByTagName('SegmentTemplate')
        elems.extend(root.getElementsByTagName('SegmentURL'))

        for e in elems:
            def process_attrib(attrib):
                if attrib not in e.attributes.keys():
                    return

                url = e.getAttribute(attrib)

                if url.startswith('http'):
                    e.setAttribute(attrib, PROXY_PATH + url)
                #     pattern = '^' + re.escape(url)
                # else:
                #     pattern = '.*' + re.escape(urljoin('.', url))

                # pattern = pattern.replace('\$RepresentationID\$', '(?P<RepresentationID>.+?)')
                # pattern = re.sub(r'\\\$Number.*?\\\$', '(?P<Number>[0-9]+?)', pattern)
                # pattern += '$'
                # pattern = re.compile(pattern)

                # template = url.replace('$RepresentationID$', '%(RepresentationID)s')
                # match    = re.search('(\$Number(.*?)\$)', template)

                # if match:
                #     if match.group(2):
                #         template = template.replace(match.group(0), match.group(2).replace('%', '%(Number)'))
                #     else:
                #         template = template.replace(match.group(0), '%(Number)d')

                # patterns[response.url][url] = {'pattern': pattern, 'template': template, 'cached': {}, 'base_urls': base_urls}

            process_attrib('initialization')
            process_attrib('media')

        response.stream.set(root.toxml(encoding='utf-8'))

    def _default_audio_fix(self, m3u8):
        if '#EXT-X-MEDIA' not in m3u8:
            return m3u8

        def _process_media(line):
            attribs = {}

            for key, value in re.findall('([\w-]+)="?([^",]*)[",$]?', line):
                attribs[key.upper()] = value.strip()

            return attribs

        default_groups = []
        groups = defaultdict(list)
        for line in m3u8.splitlines():
            if line.startswith('#EXT-X-MEDIA'):
                attribs = _process_media(line)

                # FIX es-ES fr-FR languages #
                language = attribs.get('LANGUAGE')
                if language:
                    split = language.split('-')
                    if len(split) > 1 and split[1].lower() == split[0].lower():
                        attribs['LANGUAGE'] = split[0]
                #############################

                groups[attribs['GROUP-ID']].append([attribs, line])
                if attribs.get('DEFAULT') == 'YES' and attribs['GROUP-ID'] not in default_groups:
                    default_groups.append(attribs['GROUP-ID'])

        default_language = self.headers.get('_proxy_default_language')

        if default_language:
            for group_id in groups:
                if group_id in default_groups:
                    continue

                languages = []
                for group in groups[group_id]:
                    attribs, line = group
                    
                    attribs['AUTOSELECT'] = 'NO'
                    attribs['DEFAULT']    = 'NO'

                    if attribs['LANGUAGE'] not in languages or attribs.get('TYPE') == 'SUBTITLES':
                        attribs['AUTOSELECT'] = 'YES'

                        if attribs['LANGUAGE'] == default_language:
                            attribs['DEFAULT'] = 'YES'

                        languages.append(attribs['LANGUAGE'])

        for group_id in groups:
            for group in groups[group_id]:
                attribs, line = group

                new_line = '#EXT-X-MEDIA:'
                for key in attribs:
                    new_line += u'{}="{}",'.format(key, attribs[key])

                new_line = new_line.rstrip(',')
                m3u8 = m3u8.replace(line, new_line)

        return m3u8

    def _parse_m3u8(self, response):
        m3u8 = response.stream.read().decode('utf8')
        is_master = '#EXT-X-STREAM-INF' in m3u8

        ## FIX AES-128 streams with KEYFORMAT
        ## Fixed with this PR: https://github.com/peak3d/inputstream.adaptive/pull/461
        m3u8 = m3u8.replace('KEYFORMAT="identity"', 'KEYFORMAT=""')

        try:
            m3u8 = self._default_audio_fix(m3u8)
        except Exception as e:
            log.exception(e)
        else:
            log.debug('Proxy: Default audio fixed')

        m3u8 = re.sub(r'^/', r'{}'.format(urljoin(response.url, '/')), m3u8, flags=re.I|re.M)
        m3u8 = re.sub(r'(https?)://', r'{}\1://'.format(PROXY_PATH), m3u8, flags=re.I)

        response.stream.set(m3u8.encode('utf8'))

    def _proxy_request(self, method, url):
        parsed = urlparse(url)

        headers = {}
        for header in self.headers:
            key = header.lower()
            if key not in REMOVE_IN_HEADERS:
                headers[key] = self.headers[header]

        headers['host'] = parsed.hostname
        headers.update(self._override_headers)

        length    = int(headers.get('content-length', 0))
        post_data = self.rfile.read(length) if length else None

        session = sessions.get(headers['host'], Session())
        sessions[headers['host']] = session

        if len(sessions) > 5:
            sessions.popitem(last=False)

        devlog('{} OUT: {}'.format(method.upper(), url))
            
        response = session.request(method=method, url=url, headers=headers, data=post_data, allow_redirects=False, stream=True)
        response.stream = ResponseStream(response, self._chunk_size)

        headers = {}
        for header in response.headers:
            headers[header.lower()] = response.headers[header]

        if 'location' in headers:
            headers['_orig_location'] = headers['location']

            if not headers['location'].lower().startswith('http'):
                headers['location'] = urljoin(url, headers['location'])

            headers['location']  = PROXY_PATH + headers['location']

        response.headers = headers

        return response

    def _output_headers(self, response):
        self.send_response(response.status_code)

        for header in REMOVE_OUT_HEADERS:
            response.headers.pop(header, None)

        for d in list(response.headers.items()):
            self.send_header(d[0], d[1])

        self.end_headers()

    def _output_response(self, response):
        self._output_headers(response)

        for chunk in response.stream.iter_content():
            try: self.wfile.write(chunk)
            except ConnectionResetError: break

    def do_HEAD(self):
        url = self._get_url()
        devlog('HEAD IN: {}'.format(url))
        response = self._proxy_request('HEAD', url)
        self._output_response(response)

    def do_POST(self):
        url = self._get_url()
        devlog('POST IN: {}'.format(url))
        response = self._proxy_request('POST', url)
        self._output_response(response)

    # def _cache(self, response, output=False):
    #     if output:
    #         self._output_headers(response)

    #     filepath = os.path.join(PROXY_CACHE, str(uuid.uuid4()))

    #     try:
    #         f = open(filepath, 'wb')
    #     except:
    #         f = None

    #     for chunk in response.stream.iter_content():
    #         if output:
    #             try: 
    #                 self.wfile.write(chunk)
    #             except ConnectionResetError:
    #                 f = None
    #                 break
            
    #         if f:
    #             try: f.write(chunk)
    #             except: f = None

    #         elif not output:
    #             break

    #     if not f:
    #         devlog('Cache failed')
    #         try: os.remove(filepath)
    #         except: pass
    #         return False

    #     devlog('Cached!')
    #     return filepath

    # def _search_patterns(self, url):
    #     for key in patterns:
    #         pattern = patterns[key]
    #         for key2 in pattern:
    #             match = pattern[key2]['pattern'].match(url)
    #             if match:
    #                 return self._download_segment(pattern[key2], match.groupdict())

    #     return False

    # def _remove_cache(self, key):
    #     cached = self.cached.pop(key, None)
    #     if not cached:
    #         return

    #     try: os.remove(cached['file_path'])
    #     except: pass

    # def _check_cache(self, key):
    #     cached = self.cached.get(key)

    #     try:
    #         if not cached or not os.path.exists(cached['file_path']):
    #             return False
    #     except:
    #         return False

    #     if cached.get('expires') and cached['expires'] < time.time():
    #         devlog('Cache Expired')
    #         self._remove_cache(key)
    #         return False

    #     devlog('Cache Hit')

    #     self.send_response(200)

    #     for key in cached['headers']:
    #         self.send_header(key, cached['headers'][key])

    #     self.end_headers()

    #     with open(cached['file_path'], 'rb') as f:
    #         shutil.copyfileobj(f, self.wfile, length=self._chunk_size)

    #     return True

    # def _download_segment(self, pattern, params):
    #     params['Number'] = int(params.get('Number', -1))
    #     if self._check_cache(pattern['cached'], params['Number']):
    #         return True

    #     seg_url = pattern['template'] % params

    #     if seg_url.startswith('http'):
    #         response = self._proxy_request('GET', seg_url)
    #     else:
    #         good_base = pattern['base_urls'][0]

    #         for base_url in pattern['base_urls']:
    #             response = self._proxy_request('GET', urljoin(base_url, seg_url))
    #             if response.ok:
    #                 good_base = base_url
    #                 break

    #         pattern['base_urls'].remove(good_base)
    #         pattern['base_urls'].insert(0, good_base)
            
    #     if params['Number'] > -1 and response.ok and PROXY_CACHE_BEHIND > 0:
    #         file_path = self._cache(response, output=True)  #if want to cache what we have watched (maybe cache either side of current segment for nice rewind)
    #         pattern['cached'][params['Number']] = {'file_path': file_path, 'headers': response.headers}
    #     else:
    #         self._output_response(response)
        
    #     return True

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Proxy(object):
    def __init__(self):
        if not os.path.exists(PROXY_CACHE):
            os.makedirs(PROXY_CACHE)

    def start(self):
        self._server = ThreadedHTTPServer((HOST, PORT), RequestHandler)
        self._httpd_thread = threading.Thread(target=self._server.serve_forever)
        self._httpd_thread.start()

    def stop(self):
        log.debug("Stopping Proxy Server")
        self._server.shutdown()
        self._server.server_close()
        self._server.socket.close()
        self._httpd_thread.join()