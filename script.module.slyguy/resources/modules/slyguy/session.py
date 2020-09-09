import requests

from . import userdata, settings
from .log import log

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36',
}

# from .settings import common_settings
# PROXY_PATH = 'http://{}:{}/'.format(common_settings.get('proxy_host'), common_settings.getInt('proxy_port'))

class Session(requests.Session):
    def __init__(self, headers=None, cookies_key=None, base_url='{}', timeout=None, attempts=None, verify=None):
        super(Session, self).__init__()

        self._headers     = headers or {}
        self._cookies_key = cookies_key
        self._base_url    = base_url
        self._timeout     = timeout or settings.getInt('http_timeout', 30)
        self._attempts    = attempts or settings.getInt('http_retries', 2)
        self._verify      = verify if verify is not None else settings.getBool('verify_ssl', True)

        self.headers.update(DEFAULT_HEADERS)
        self.headers.update(self._headers)

        if self._cookies_key:
            self.cookies.update(userdata.get(self._cookies_key, {}))

    def request(self, method, url, timeout=None, attempts=None, verify=None, **kwargs):
        if not url.startswith('http'):
            url = self._base_url.format(url)

        timeout = timeout or self._timeout
        if timeout:
            kwargs['timeout'] = timeout

        kwargs['verify']  = verify or self._verify
        attempts          = attempts or self._attempts

        #url = PROXY_PATH + url

        for i in range(1, attempts+1):
            try:
                log('Attempt {}/{}: {} {} {}'.format(i, attempts, method, url, kwargs if method.lower() != 'post' else ""))
            except:
                log('Attempt {}/{}: {} {}'.format(i, attempts, method, url))

            try:
                return super(Session, self).request(method, url, **kwargs)
            except:
                if i == attempts:
                    raise

    def save_cookies(self):
        if not self._cookies_key:
            raise Exception('A cookies key needs to be set to save cookies')

        userdata.set(self._cookies_key, self.cookies.get_dict())

    def clear_cookies(self):
        if self._cookies_key:
            userdata.delete(self._cookies_key)
        self.cookies.clear()

    def chunked_dl(self, url, dst_path, method='GET', chunksize=None, **kwargs):
        kwargs['stream'] = True
        resp = self.request(method, url, **kwargs)
        resp.raise_for_status()

        with open(dst_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=chunksize or settings.getInt('chunksize', 4096)):
                f.write(chunk)