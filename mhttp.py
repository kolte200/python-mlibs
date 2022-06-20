import socket
import time
import ssl
import gzip


default_get_header = {}
default_get_header["Accept"] = "*/*"
default_get_header['Accept-Encoding'] = "gzip"

default_post_header = {}
default_post_header["Accept"] = "*/*"
default_post_header["Content-Type"] = "application/x-www-form-urlencoded"
default_post_header['Accept-Encoding'] = "gzip"

port_of_proto = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
    "ftp": 21,
    "sftp": 22,
    "smtp": 25,
    "ssh": 22,
    "rtsp": 554,
    "telnet": 23,
    "ldap": 389,
    "ldaps": 636
}

RECV_MAXSIZE = 4096

redirect_codes = [300, 301, 302, 303]

_sslcontext = ssl.create_default_context()


def bytesDecode(data):
    return data.decode('utf-8', errors='ignore')

def remTrailingSpace(a):
    i = 0
    m = len(a)

    while i < m and a[i] == ' ': i += 1

    out = ""
    tmp = ""
    while i < m:
        c = a[i]
        if c == ' ':
            tmp += c
        else:
            if tmp:
                out += tmp
                tmp = ""
            out += c
        i += 1
    
    return out


def parseURL(url):
    # Protocol
    protocol = 'http'
    start_pos = url.find('://')
    if start_pos == -1:
        start_pos = 0
    else:
        protocol = url[:start_pos]
        start_pos += 3
    
    # Path
    pos = url.find('/', start_pos)
    dns = ''
    path = '/'
    if pos == -1:
        dns = url[start_pos:]
    else:
        dns = url[start_pos:pos]
        path = url[pos:]

    # Authentification
    pos = dns.find('@')
    username = ''
    password = ''
    has_auth = False
    if pos != -1:
        username = dns[:pos]
        dns = dns[pos+1:]
        has_auth = True
        pos = username.find(':')
        if pos != -1:
            username = username[:pos]
            password = username[pos+1:]
    
    # Port
    pos = dns.rfind(':')
    port = None
    if pos == -1 and (protocol in port_of_proto):
        port = port_of_proto[protocol]
    else:
        port = int(dns[pos+1:])
        dns = dns[:pos]
    
    return {'path':path, 'dns':dns, 'proto':protocol, 'ip':socket.gethostbyname(dns), 'port':port, 'hascredentials':has_auth, 'password':password, 'username':username}


def parseSetCookieAttr(attr):
    pos = attr.find('=')
    if pos == -1:
        return attr, None
    return attr[:pos], attr[pos + 1:]

def parseSetCookie(data):
    attrs = data.split("; ")

    if len(attrs) < 1:
        return None

    name, content = parseSetCookieAttr(attrs[0])
    httponly = False
    secure = False
    path = None
    domain = None
    maxage = None
    expires = None
    samesite = None

    for i in range(1, len(attrs)):
        key, value = parseSetCookieAttr(attrs[i])

        if key == "HttpOnly":
            httponly = True
        elif key == "Secure":
            secure = True
        elif key == "Path":
            path = value
        elif key == "Domain":
            path = value
        elif key == "Max-Age":
            maxage = value
        elif key == "Expires":
            expires = value
        elif key == "SameSite":
            samesite = value

    return {
        'name': name,
        'content': content,
        'httponly': httponly,
        'secure': secure,
        'path': path,
        'domain': domain,
        'maxage': maxage,
        'expires': expires,
        'samesite': samesite
    }


def formatCookies(cookies):
    return "; ".join(["%s=%s" % (cookie['name'], cookie['content']) for cookie in cookies])


# Parse steps for request and response
HTTP_STEP_REPVER   = 0x0
HTTP_STEP_REPCODE  = 0x1
HTTP_STEP_REPMSG   = 0x2
HTTP_STEP_HDRKEY   = 0x3
HTTP_STEP_HDRVALUE = 0x4
HTTP_STEP_CHECKEND = 0x5
HTTP_STEP_METHOD   = 0x6
HTTP_STEP_PATH     = 0x7
HTTP_STEP_REQVER   = 0x8

# Parse utils functions
def parseUntilChar(txt, sep, i, m, ret):
    while i < m:
        c = txt[i]
        if c == sep:
            return ret, i+1, True
        ret.append(c)
        i += 1
    return ret, i, False

def parseUntilTwoChar(txt, sep1, sep2, i, m, ret):
    x = m - 1
    while i < x:
        c = txt[i]
        if c == sep1 and txt[i+1] == sep2:
            return ret, i+2, True
        ret.append(c)
        i += 1
    return ret, i, False

# Common parse functions
def parseHdrKey(rep, i, m, key):
    return parseUntilChar(rep, ord(':'), i, m, key)

def parseHdrValue(rep, i, m, value):
    return parseUntilTwoChar(rep, ord('\r'), ord('\n'), i, m, value)

def parseCheckEnd(rep, i, m):
    if i < m-1:
        if rep[i] == ord('\r') and rep[i+1] == ord('\n'):
            return True, i+2, True
        return False, i, True
    return False, i, False

# Response parse functions
def parseRepVersion(rep, i, m, version):
    return parseUntilChar(rep, ord(' '), i, m, version)

def parseRepCode(rep, i, m, code):
    return parseUntilChar(rep, ord(' '), i, m, code)

def parseRepMsg(rep, i, m, msg):
    return parseUntilTwoChar(rep, ord('\r'), ord('\n'), i, m, msg)

def parseRepHeader(rep, i, m, step, ver, code, msg, key, val, hdrs=[]):
    complet = False

    while not complet:
        if   step == HTTP_STEP_REPVER:
            ver, i, finish = parseRepVersion(rep, i, m, ver)
            if finish: step = HTTP_STEP_REPCODE
            else: break
        
        elif step == HTTP_STEP_REPCODE:
            code, i, finish = parseRepCode(rep, i, m, code)
            if finish: step = HTTP_STEP_REPMSG
            else: break
        
        elif step == HTTP_STEP_REPMSG:
            msg, i, finish = parseRepMsg(rep, i, m, msg)
            if finish: step = HTTP_STEP_CHECKEND
            else: break
        
        elif step == HTTP_STEP_CHECKEND:
            complet, i, finish = parseCheckEnd(rep, i, m)
            if finish: step = HTTP_STEP_HDRKEY
            else: break
        
        elif step == HTTP_STEP_HDRKEY:
            key, i, finish = parseHdrKey(rep, i, m, key)
            if finish: step = HTTP_STEP_HDRVALUE
            else: break
        
        elif step == HTTP_STEP_HDRVALUE:
            val, i, finish = parseHdrValue(rep, i, m, val)
            if finish:
                step = HTTP_STEP_CHECKEND
                hdrs.append(( remTrailingSpace(bytesDecode(key).lower()), remTrailingSpace(bytesDecode(val)) ))
                key.clear()
                val.clear()
            else: break
    
    return i, step, ver, code, msg, key, val, hdrs, complet

# Request parse functions
def parseReqMethod(rep, i, m, method):
    return parseUntilChar(rep, ord(' '), i, m, method)  

def parseReqPath(rep, i, m, path):
    return parseUntilChar(rep, ord(' '), i, m, path) 

def parseReqVersion(rep, i, m, version):
    return parseUntilTwoChar(rep, ord('\r'), ord('\n'), i, m, version)

def parseReqHeader(rep, i, m, step, met, path, ver, key, val, hdrs=[]):
    complet = False

    while not complet and i < m:
        if   step == HTTP_STEP_METHOD:
            met, i, finish = parseReqMethod(rep, i, m, met)
            if finish: step = HTTP_STEP_PATH
            else: break
        
        elif step == HTTP_STEP_PATH:
            path, i, finish = parseReqPath(rep, i, m, path)
            if finish: step = HTTP_STEP_REQVER
            else: break
        
        elif step == HTTP_STEP_REQVER:
            ver, i, finish = parseReqVersion(rep, i, m, ver)
            if finish: step = HTTP_STEP_CHECKEND
            else: break
        
        elif step == HTTP_STEP_CHECKEND:
            complet, i, finish = parseCheckEnd(rep, i, m)
            if finish: step = HTTP_STEP_HDRKEY
            else: break
        
        elif step == HTTP_STEP_HDRKEY:
            key, i, finish = parseHdrKey(rep, i, m, key)
            if finish: step = HTTP_STEP_HDRVALUE
            else: break
        
        elif step == HTTP_STEP_HDRVALUE:
            val, i, finish = parseHdrValue(rep, i, m, val)
            if finish:
                step = HTTP_STEP_CHECKEND
                hdrs.append(( remTrailingSpace(bytesDecode(key).lower()), remTrailingSpace(bytesDecode(val)) ))
                key.clear()
                val.clear()
            else: break
    
    return i, step, met, path, ver, key, val, hdrs, complet


# Header utils functions
def addHeader(headers, key, value):
    headers.append((key.lower(), value))

def hasHeader(header, key):
    key = key.lower()
    for k, _ in header:
        if k == key:
            return True
    return False

def getHeaderValue(header, key):
    key = key.lower()
    for k, v in header:
        if k == key:
            return v
    return None

def getHeader(headers, key):
    return getHeaderValue(headers, key)

def getHeaderValues(header, key):
    key = key.lower()
    vals = []
    for k, v in header:
        if k == key:
            vals.append(v)
    return vals


# Main HTTP class
class HTTP():
    def __init__(self, s=None, keep_alive=False):
        self.sockets = {}
        self.defaultkeepalive = keep_alive
        self.recv_callback = None
    
    def recvTimeout(self, s, packet_size, timeout):
        s.setblocking(0)
        end_time = time.time()+timeout
        data = b''
        while not data:
            try:
                data = s.recv(packet_size)
            except:
                pass
            if time.time() > end_time:
                break
        return data


    def readResponse(self, s):
        step, version, repcode, repmsg, key, val, headers = HTTP_STEP_REPVER, bytearray(), bytearray(), bytearray(), bytearray(), bytearray(), []
        complet = False
        data = bytearray()
        body = bytearray()
        
        i = 0
        while not complet:
            x = s.recv( RECV_MAXSIZE )
            if not x: break
            data += x
            i, step, version, repcode, repmsg, key, val, headers, complet = parseRepHeader(data, i, len(data), step, version, repcode, repmsg, key, val, headers)

        if complet:
            if i < len(data):
                body = data[i:]
            repcode = int(repcode)
            return False, bytesDecode(version), int(repcode), bytesDecode(repmsg), headers, body

        return True, None, None, None, None, None
    
    def readRequest(self, s):
        step, version, method, path, key, val, headers = HTTP_STEP_METHOD, b'', b'', b'', b'', b'', []
        complet = False
        data = b''
        body = b''
        
        i = 0
        while not complet:
            x = s.recv( RECV_MAXSIZE )
            if not x: break
            data += x
            i, step, method, path, version, key, val, headers, complet = parseReqHeader(data, i, len(data), step, method, path, version, key, val, headers)

        if complet and i < len(data):
            body = data[i:]
            return False, bytesDecode(method), bytesDecode(path), bytesDecode(version), headers, body

        return True, None, None, None, None, None

    def readBody(self, s, headers, body):
        # Read all body
        if getHeader(headers, 'transfer-encoding') == 'chunked':
            body = self.recvAllChunked(s, body)
        elif hasHeader(headers, 'content-length'):
            bodylen = int( getHeader(headers, 'content-length') )
            if len(body) < bodylen:
                body += self.recvAllSized(s, bodylen - len(body))
        else:
            body += self.recvAllTimeout(s)
        
        # Decompress when body encoded
        if body and hasHeader(headers, 'content-encoding'):
            encoding = getHeader(headers, 'content-encoding')
            if encoding == "gzip":
                body = gzip.decompress( body )
            else:
                print("HTTP: Warning: Unsuported content encoding: " + encoding)
        
        return body


    def recvAllSized(self, s, total_size):
        actual_size = 0
        data = b''
        while actual_size < total_size:
            temp_data = s.recv(min(4096, total_size-actual_size))
            actual_size += len(temp_data)
            data += temp_data
        return data
    
    def recvAllChunked(self, s, last_part=None):
        actual_size = 0
        data = b''
        temp_data = b''
        if last_part != None: temp_data = last_part
        cursor = 0
        part = 0
        chunk_hdr = ''
        chunk_len = 0
        start_of_chunk = 0
        recv_len = len(temp_data)
        while 1:
            if cursor >= len(temp_data)-1:
                d = s.recv(4096)
                if not d: return data
                temp_data += d
                recv_len = len(temp_data)
            else:
                if part == 0:
                    if temp_data[cursor:cursor+2] != b'\r\n':
                        chunk_hdr += chr(temp_data[cursor])
                        cursor += 1
                    else:
                        chunk_len = int(chunk_hdr, 16)
                        if chunk_len == 0: return data
                        part = 1
                        cursor += 2
                        start_of_chunk = cursor
                
                elif part == 1:
                    already_read = cursor-start_of_chunk
                    if recv_len-cursor < chunk_len-already_read:
                        data += temp_data[cursor:]
                        cursor += recv_len-cursor
                    else:
                        data += temp_data[cursor:start_of_chunk+chunk_len]
                        cursor += chunk_len-already_read+2
                        part = 0
                        chunk_hdr = ''
                        
    def recvAllTimeout(self, s):
        data = b''
        temp_data = self.recvTimeout(s, 4096, 0.05)
        while temp_data:
            data += temp_data
            temp_data = self.recvTimeout(s, 4096, 0.05)
        return data
    

    def formatRequest(self, method, path, header, data):
        ret = b''
        out = '%s %s HTTP/1.1\r\n'%(method, path)
        for k in header:
            out += k + ': ' + header[k] + '\r\n'
        out += '\r\n'
        ret += out.encode('ascii')
        if data is not None:
            ret += data
        return ret

    def formatResponse(self, code, msg_code, header, data):
        ret = b''
        out = 'HTTP/1.1 %s %s\r\n'%(str(code), msg_code)
        for k in header:
            out += k + ': ' + header[k] + '\r\n'
        out += '\r\n'
        ret += out.encode('ascii')
        if data != None: ret += data.encode('utf8')
        return ret
    

    def closeAllConnection(self):
        for sock in self.sockets.values():
            if sock is not None:
                sock.close()

    def closeConnection(self, sock, dns):
        if sock is not None:
            sock.close()
        if dns in self.sockets:
            del self.sockets[dns]
    

    def newSocket(self, use_ssl=False, hostname=None):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if use_ssl:
            sock = _sslcontext.wrap_socket(sock, server_hostname=hostname)
        return sock


    def _request(self, url_infos, method, keep_alive, timeout, header, data):
        use_ssl = True if url_infos['proto'] == 'https' else False
        dns = url_infos['dns']
        sock = None
        request = self.formatRequest(method, url_infos['path'], header, data)

        # Send HTTP request
        if dns in self.sockets and self.sockets[dns] is not None:
            sock = self.sockets[dns]
            try:
                sock.send( request )
            except ConnectionResetError:
                sock = self.newSocket(use_ssl, dns)
                sock.connect((dns, url_infos['port']))
                sock.send( request )
        else:
            sock = self.newSocket(use_ssl, dns)
            sock.connect((dns, url_infos['port']))
            sock.send( request )
        
        # Read HTTP response
        error, version, repcode, repmsg, headers, body  = self.readResponse(sock)
        if error: return None

        body = self.readBody(sock, headers, body)
        
        if getHeader(headers, 'connection') == 'close' or not keep_alive:
            self.closeConnection(sock, dns)
        
        return {'version': version, 'repcode': repcode, 'repmsg': repmsg, 'header': headers, 'body': bytes(body)}


    def request(self, url, method="GET", keep_alive=None, timeout=6, follow_redirect=True, header=None, data=None):
        method = method.upper()

        if header is None:
            if method == "POST": header = default_post_header.copy()
            else: header = default_get_header.copy()

        if keep_alive is None:
            keep_alive = self.defaultkeepalive
        
        url_infos = parseURL(url)

        header['Host'] = url_infos['dns']
        header['Connection'] = "keep-alive" if keep_alive else "close"
        
        if data != None:
            if data is not bytes:
                data = data.encode('utf8')
            header["Content-Length"] = str(len(data))

        rep = self._request(url_infos, method, keep_alive, timeout, header, data)
        last_base_url = url_infos['proto']+'://'+url_infos['dns']

        if follow_redirect:
            while 1:
                if rep['repcode'] in redirect_codes and hasHeader(rep['header'], 'Location'):
                    loc = getHeader(rep['header'], 'Location')
                    if loc[0] == '/':
                        loc = last_base_url + loc
                    url_infos = parseURL(loc)
                    last_base_url = url_infos['proto']+'://'+url_infos['dns']
                    
                    #print("Redirect to: "+loc)
                    rep = self._request(url_infos, method, keep_alive, timeout, header, data)
                else:
                    break
        return rep



# Test code
'''
http = HTTP()
print( http.request("https://httpbin.org/get") )
'''
