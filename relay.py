import tornado.ioloop
import tornado.httpserver
import tornado.web
import tornado.iostream
import functools
import uuid
import sys
import socket
import base64
import logging

logger = logging.getLogger('Hashi Relay')
#logging.basicConfig(level=logging.INFO)

def websafe_to_base64(s):
    s = s.replace('-', '+')
    s = s.replace('_', '/')

    mod4 = len(s) % 4
    if mod4 == 2:
        s += '=='
    elif mod4 == 3:
        s += '='
    elif mod4 == 1:
        raise Exception('invalid websafe string')
    return s


def base64_to_websafe(s):
    s = s.replace('+', '-')
    s = s.replace('/', '_')
    return s.replace('=', '')


class RelayAgent(object):
    ERROR = -1
    CREATED = 0
    CONNECTED = 1
    CLOSED = 2

    def __init__(self, sid, host, port):
        self.sid = sid
        self.host = host
        self.port = port
        self.reset()

    def set_close_callback(self, callback):
        self.close_callback = callback

    def reset(self):
        # init
        self.status = RelayAgent.CREATED
        self.read_callback = None
        self.close_callback = None
        self.stream = None
        self.buf_read = ''
        self.buf_write = ''

    def connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.stream = tornado.iostream.IOStream(s)
        self.stream.connect((self.host, self.port), self._connected)

    def _connected(self):
        logger.info('connected')
        self.status = RelayAgent.CONNECTED
        self.stream.set_close_callback(self._closed)
        self.stream.read_until_close(self._read_final_callback, self._streaming_read)
        if len(self.buf_write):
            self.stream.write(self.buf_write)
            self.buf_write = ''

    def _closed(self):
        self.status = RelayAgent.CLOSED
        if self.close_callback:
            self.close_callback(self)

    def _read_final_callback(self, data):
        pass

    def _streaming_read(self, data):
        self.buf_read += data
        if self.read_callback is not None:
            self.read_callback(self.buf_read)
            self.buf_read = ''
            self.read_callback = None

    def read(self, callback):
        if len(self.buf_read):
            callback(self.buf_read)
            self.buf_read = ''
            self.read_callback = None
        else:
            self.read_callback = callback

    def write(self, data):
        if self.status == RelayAgent.CONNECTED:
            self.stream.write(data)
        else:
            self.buf_write += data

    def is_usable(self):
        return self.status != RelayAgent.CLOSED and self.status != RelayAgent.ERROR


class RelayAgentPool(object):
    def __init__(self):
        self._agents = {}

    def create_agent(self, host, port):
        sid = uuid.uuid4().hex
        agent = RelayAgent(sid, host, port)
        self._agents[sid] = agent
        return agent

    def get_agent(self, sid):
        if sid in self._agents:
            return self._agents[sid]
        else:
            return None


class CookieHandler(tornado.web.RequestHandler):
    def get(self):
        ext = self.get_argument('ext')
        path = self.get_argument('path')
        scheme = 'chrome-extension'
        relay_user = 'relay_user'
        relay_host = self.request.host
        idx = relay_host.find(':')
        if idx != -1:
            relay_host = relay_host[:idx]
        self.set_cookie('auth_token', uuid.uuid4().hex) # authentication is not implemented
        return self.redirect("%s://%s/%s#%s@%s" % (scheme, ext, path, relay_user, relay_host))


class CrossDomainHandler(tornado.web.RequestHandler):
    def prepare(self):
        origin = self.request.headers.get('origin', '*')
        self.set_header('Access-Control-Allow-Origin', origin)
        self.set_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.set_header('Access-Control-Max-Age', 1000)
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Headers', '*')


class RelayProxyHandler(CrossDomainHandler):
    def get(self):
        host = self.get_argument('host')
        port = int(self.get_argument('port'))
        agent = pool.create_agent(host, port)
        agent.connect()
        self.write(agent.sid)


class RelayReadHandler(CrossDomainHandler):
    @tornado.web.asynchronous
    def get(self):
        sid = self.get_argument('sid')
        agent = pool.get_agent(sid)
        if agent is None or not agent.is_usable():
            self.send_error(410)
            return
        agent.read(self._on_read)

    def _on_read(self, data):
        self.write(base64_to_websafe(base64.b64encode(data)))
        self.finish()


class RelayWriteHandler(CrossDomainHandler):
    def get(self):
        sid = self.get_argument('sid')
        agent = pool.get_agent(sid)
        if agent is None or not agent.is_usable():
            self.send_error(410)
            return
        data = base64.b64decode(websafe_to_base64(self.get_argument('data')))
        agent.write(data)
        self.write('OK')


pool = RelayAgentPool()

cookie_app = tornado.web.Application([
    (r"/cookie", CookieHandler),
])

relay_app = tornado.web.Application([
    (r"/proxy", RelayProxyHandler),
    (r"/read", RelayReadHandler),
    (r"/write", RelayWriteHandler),
])

if __name__ == "__main__":
    relay_app.listen(8023)
    cookie_app.listen(8022)
    tornado.ioloop.IOLoop.instance().start()
