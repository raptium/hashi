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

logger = logging.getLogger('jobson relay')
logging.basicConfig(level=logging.INFO)

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

    def __init__(self):
        self._clients = {}

    def new_client(self, session_id, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        stream = tornado.iostream.IOStream(s)
        client = {'stream': stream, 'read_callback': None, 'connected': False, 
            'write_buffer': '', 'read_buffer': ''}
        self._clients[session_id] = client
        stream.connect((host, port), functools.partial(self._connected, session_id=session_id, stream=stream))

    def _connected(self, session_id, stream):
        client = self._clients[session_id]
        stream.set_close_callback(functools.partial(self._closed, session_id=session_id))
        stream.read_until_close(self._read_final_callback, functools.partial(self._streaming_read, session_id=session_id))
        client['connected'] = True
        if len(client['write_buffer']) > 0:
            stream.write(client['write_buffer'])
            client['write_buffer'] = ''

    def _streaming_read(self, data, session_id):
        client = self._clients[session_id]
        client['read_buffer'] += data
        if client['read_callback'] is not None:
            client['read_callback'](client['read_buffer'])
            client['read_buffer'] = ''
            client['read_callback'] = None

    def _closed(self, session_id):
        del self._clients[session_id]

    def read(self, session_id, callback):
        client = self._clients[session_id]
        if len(client['read_buffer']):
            callback(client['read_buffer'])
            client['read_buffer'] = ''
            client['read_callback'] = None
        else:
            client['read_callback'] = callback


    def _read_final_callback(self, data):
        logger.info(data)

    def write(self, session_id, data):
        client = self._clients[session_id]
        if not client['connected']:
            client['write_buffer'] += data
        else:
            client['stream'].write(data)


class CookieHandler(tornado.web.RequestHandler):

    def get(self):
        ext = self.get_argument('ext')
        path = self.get_argument('path')
        scheme = 'chrome-extension'
        relay_user = 'haro'
        relay_host = '192.168.77.32'
        self.set_cookie('_relay_session_id', uuid.uuid4().hex)
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
        session_id = self.get_cookie('_relay_session_id')
        logger.info('session_id: %s', session_id)
        agent.new_client(session_id, host, port)
        logger.info(agent._clients)
        self.write(session_id)

        
class RelayReadHandler(CrossDomainHandler):


    @tornado.web.asynchronous
    def get(self):
        session_id = self.get_argument('sid')
        agent.read(session_id, self._on_read)
        self.set_status(200)
        self.flush()
        logger.info('start hanging GET request')

    def _on_read(self, data):
        logger.info('%d bytes read', len(data))
        self.write(base64_to_websafe(base64.b64encode(data)))
        logger.info(base64_to_websafe(base64.b64encode(data)))
        self.flush()
        self.finish()

class RelayWriteHandler(CrossDomainHandler):

    def get(self):
        logger.info('write request received')
        session_id = self.get_argument('sid')
        data = base64.b64decode(websafe_to_base64(self.get_argument('data')))
        logger.info('%d bytes written', len(data))
        agent.write(session_id, data)
        self.write('OK')

        

agent = RelayAgent()

cookie_app = tornado.web.Application([
    (r"/cookie", CookieHandler),
], debug=True)

relay_app = tornado.web.Application([
    (r"/proxy", RelayProxyHandler),
    (r"/read", RelayReadHandler),
    (r"/write", RelayWriteHandler),
], debug=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        relay_app.listen(8023)
    else:
        cookie_app.listen(8022)
    tornado.ioloop.IOLoop.instance().start()

