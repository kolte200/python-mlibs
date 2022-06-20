from sys import stderr
from xmlrpc.client import Boolean


# Errors

JSONC_ERROR_UNKNOW = 0
JSONC_ERROR_SUCCESS = 1
JSONC_ERROR_STR_NEWLINE = 3
JSONC_ERROR_UNEXPECTED_KV_SEP = 4
JSONC_ERROR_UNEXPECTED_NODE_SEP = 5
JSONC_ERROR_UNEXPECTED_ARRAY_SEP = 6
JSONC_ERROR_TWO_POINTS_IN_NUMBER = 7
JSONC_ERROR_UNQUOTED_KEY = 8
JSONC_ERROR_UNKNOWN_KEYWORD = 9
JSONC_ERROR_CHAR_AT_END = 10
JSONC_ERROR_EMPTY_NODE_ENTRY = 11
JSONC_ERROR_EMPTY_ARRAY_ENTRY = 12
JSONC_ERROR_EMPTY_DATA = 13



# Error messages
error2str = {
    JSONC_ERROR_UNKNOW: 'unknow',
    JSONC_ERROR_SUCCESS: 'no error',
    JSONC_ERROR_STR_NEWLINE: 'new line character in single line string',
    JSONC_ERROR_UNEXPECTED_KV_SEP: 'unexpected separator between key and value',
    JSONC_ERROR_UNEXPECTED_NODE_SEP: 'unexpected node\' elements separator',
    JSONC_ERROR_UNEXPECTED_ARRAY_SEP: 'unexpected array\'s elements separator',
    JSONC_ERROR_TWO_POINTS_IN_NUMBER: 'two point in a floating point number',
    JSONC_ERROR_UNQUOTED_KEY: 'unquoted key',
    JSONC_ERROR_UNKNOWN_KEYWORD: 'unknown keyword \'%s\'',
    JSONC_ERROR_CHAR_AT_END: 'unexpected char at the end of the root value',
    JSONC_ERROR_EMPTY_NODE_ENTRY: 'empty entry in object',
    JSONC_ERROR_EMPTY_ARRAY_ENTRY: 'empty entry in array',
    JSONC_ERROR_EMPTY_DATA: 'no data provided'
}

def jsoncErrorToStr(err, *args):
    return error2str[err] % args


ERROR_LINE_WIDTH = 54


class JsonCParseError(BaseException):
    def __init__(self, code=JSONC_ERROR_UNKNOW, offset=None, line=None, column=None, linestr="", args=()):
        self.error = jsoncErrorToStr(code, *args)
        self.code = code
        self.line = line
        self.column = column
        self.offset = offset
        self.args = args
        self.linestr = linestr
        self.msg = self._toString()
        super().__init__(self.msg)
    
    def _toString(self):
        msg = ""
        if self.offset is not None: msg += "offset %i, " % self.offset
        if self.line is not None: msg += "line %i, " % self.line
        if self.column is not None: msg += "column %i, " % self.column
        msg += self.error
        if self.column is not None and self.linestr:
            a = max(0, self.column - (ERROR_LINE_WIDTH // 2))
            b = min(len(self.linestr), a + ERROR_LINE_WIDTH)
            msg += "\n%s\n%s^" % (self.linestr[a:b].replace('\t', ' '), ' ' * (self.column - a))
        return msg

    def print(self):
        print("Error: " + self.msg, flush=True, file=stderr)
    
    def __eq__(self, o) -> bool:
        return self.code == o.code
    
    def __ne__(self, o: object) -> bool:
        return self.code != o.code


JSONC_SUCCESS = JsonCParseError(JSONC_ERROR_SUCCESS)


ESCAPE_CHARS = {
    'n': '\n',
    'r': '\r',
    't': '\t',
    '0': '\0'
}


JSONC_TYPE_UNKNOW = 0
JSONC_TYPE_NODE = 1
JSONC_TYPE_ARRAY = 2
JSONC_TYPE_INT = 3
JSONC_TYPE_FLOAT = 4
JSONC_TYPE_STR = 5
JSONC_TYPE_NULL = 6
JSONC_TYPE_BOOL = 7


class JsonCNode(dict):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent


class JsonCArray(list):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent


def stringify(v : str | bool | int | float | None | JsonCArray | JsonCNode ) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    elif v is None:
        return "null"
    elif isinstance(v, JsonCArray):
        r = "["
        if len(v) > 0:
            r += v[0].stringify()
            for i in range(1, len(v)):
                r += ',' + v[i].stringify()
        return r + ']'
    elif isinstance(v, JsonCNode):
        items = list(v.items())
        r = "{"
        if len(items) > 0:
            r += "\"%s\":%s" % (items[0][0], items[0][1].stringify())
            for i in range(1, len(items)):
                r += ",\"%s\":%s" % (items[i][0], items[i][1].stringify())
        return r + '}'
    elif isinstance(v, str):
        return "\"%s\"" % v
    else:
        return str(v)


def _jsonc_is_whitespace(c):
    return c in [' ', '\t', '\r', '\n']

def _jsonc_is_letter(c):
    return 'a' <= c <= 'z' or 'A' <= c <= 'Z'

def _jsonc_is_digit(c):
    return '0' <= c <= '9'


class JsonCParser:
    def __init__(self):
        self.root = None

        # Parse configuration
        self.allowOneLineComment = True
        self.allowMultiLinesComment = True
        self.allowUnquotedKey = False
        self.allowEmptyEntry = False
        self.oneLineQuotes = ['"']
        self.multiLinesQuotes = ['`']
        self.quotedKey = True
        self.nullValues = ["null"]
        self.falseValues = ["false"]
        self.trueValues = ["true"]

        # Parse context variables
        self.reset()


    def reset(self):
        self.func = self._parse_value # Called function stack
        self.line = 1 # Current character line
        self.linestr = "" # String of the current line
        self.col = 0 # Current character column
        self.offset = 0 # Character offset from the beginin of the parse
        self.data = None # Current data chunk to parse
        self.i = 0 # Index of the current character to read in data
        self.m = 0 # Max value of i (length of data)
        self.s = "" # Current readed string
        self.n = 0 # The current number readed
        self.lastfunc = None # The last executed function (to correctly resume when finished to parse comment)
        self.divisor = 1 # The divisor used for creating floating point number
        self.key = None # Current entry value
        self.node : JsonCArray | JsonCNode = None # Current node
        self.quote = None # The opening quote
        self.escape = False # If the current character to read inside a quoted string is escaped
        self.lastc = None # The alst character
        self.waitentry = False # If we are waiting for an entry inside an array or object


    def parse(self, data):
        if len(data) < 1:
            self._raise_error(JSONC_ERROR_EMPTY_DATA)
        if self.lastc is None:
            self.data = data
            self.i = 0
            self.m = len(data) - 1
        else:
            self.data = self.lastc + data
            self.i = 0
            self.m = len(data)
        self.lastc = self.data[-1]
        while self.i < self.m:
            #print("Call function '"+self.func.__name__+"'") # Debug
            self.func()


    def _raise_error(self, code, *args):
        linestr = self.linestr
        for i in range(self.i, min(self.i + ERROR_LINE_WIDTH, self.m)):
            if self.data[i] == '\n': break
            linestr += self.data[i]
        raise JsonCParseError(code, self.offset, self.line, self.col, linestr, args)


    def _next_char(self):
        if self.i >= self.m: return None
        if self.data[self.i] == '\n':
            self.line += 1
            self.col = 0
            self.linestr = ""
        else:
            self.col += 1
            self.linestr += self.data[self.i]
        self.i += 1
        self.offset += 1


    def _parse_multilines_comment(self):
        while self.i < self.m:
            c = self.data[self.i]
            if c == '*' and self.data[self.i + 1] == '/':
                self._next_char()
                self._next_char()
                self.func = self.lastfunc
                return
            self._next_char()


    def _parse_oneline_comment(self):
        while self.i < self.m:
            c = self.data[self.i]
            if c == '\n':
                self._next_char()
                self.func = self.lastfunc
                return
            self._next_char()


    def _skip_whitespaces(self):
        while self.i < self.m:
            c = self.data[self.i]
            if not _jsonc_is_whitespace(c) and c != '\0':
                if c == '/':
                    c2 = self.data[self.i + 1]
                    if self.allowOneLineComment and c2 == '/':
                        self.lastfunc = self.func
                        self._next_char()
                        self._next_char()
                        self.func = self._parse_oneline_comment
                        return False
                    elif self.allowMultiLinesComment and c2 == '*':
                        self.lastfunc = self.func
                        self._next_char()
                        self._next_char()
                        self.func = self._parse_multilines_comment
                        return False
                return True
            self._next_char()
        return False

    
    def _read_word(self):
        while self.i < self.m:
            c = self.data[self.i]
            if not _jsonc_is_letter(c):
                return True
            self.s += c
            self._next_char()
        return False


    def _read_oneLineQuote(self):
        while self.i < self.m:
            c = self.data[self.i]
            if c == '\n':
                self._raise_error(JSONC_ERROR_STR_NEWLINE)
            elif self.escape:
                if c in ESCAPE_CHARS:
                    self.s += ESCAPE_CHARS[c]
                else:
                    self.s += c
                self.escape = False
            else:
                if c == '\\':
                    self.escape = True
                elif c == self.quote:
                    self._next_char()
                    return True
                else:
                    self.s += c
            self._next_char()
        return False


    def _read_multiLinesQuote(self):
        while self.i < self.m:
            c = self.data[self.i]
            if self.escape:
                if c in ESCAPE_CHARS:
                    self.s += ESCAPE_CHARS[c]
                else:
                    self.s += c
                self.escape = False
            else:
                if c == '\\':
                    self.escape = True
                elif c == self.quote:
                    self._next_char()
                    return True
                else:
                    self.s += c
            self._next_char()
        return False


    def _read_number(self):
        while self.i < self.m:
            c = self.data[self.i]
            if self.divisor > 1:
                if _jsonc_is_digit(c):
                    self.n += (ord(c) - ord('0')) / self.divisor
                    self.divisor *= 10
                elif c == '.':
                    self._raise_error(JSONC_ERROR_TWO_POINTS_IN_NUMBER)
                else:
                    return True
            else:
                if _jsonc_is_digit(c):
                    self.n = self.n * 10 + (ord(c) - ord('0'))
                elif c == '.':
                    self.divisor = 10
                else:
                    return True
            self._next_char()
        return False


    def _parse_key_end(self):
        if self._skip_whitespaces():
            c = self.data[self.i]
            if c != ':':
                self._raise_error(JSONC_ERROR_UNEXPECTED_KV_SEP)
            self._next_char()
            self.func = self._parse_value


    def _parse_key_word(self):
        if self._read_word():
            self.key = self.s
            self.func = self._parse_key_end


    def _parse_key_quote(self):
        if self._read_oneLineQuote():
            self.key = self.s
            self.func = self._parse_key_end


    def _parse_key(self):
        c = self.data[self.i]
        self.s = ""
        self.escape = False
        if c in self.oneLineQuotes:
            self.quote = c
            self.escape = False
            self._next_char()
            self.func = self._parse_key_quote
        else:
            if not self.allowUnquotedKey:
                self._raise_error(JSONC_ERROR_UNQUOTED_KEY)
            self.func = self._parse_key_word


    def _store_value(self, val):
        #print("Store value '"+str(val.value)+"'") # Debug
        if self.node is None:
            self.node = val
            self.func = self._parse_end
        elif isinstance(self.node, JsonCArray):
            self.node.append(val)
            self.func = self._parse_array
        elif isinstance(self.node, JsonCNode):
            self.node[self.key] = val
            self.func = self._parse_node
        else:
            raise Exception("How did you get here ?!?")


    def _parse_value_oneline_str(self):
        if self._read_oneLineQuote():
            self._store_value(self.s)


    def _parse_value_multilines_str(self):
        if self._read_multiLinesQuote():
            self._store_value(self.s)


    def _parse_value_number(self):
        if self._read_number():
            self._store_value(self.n)


    def _parse_value_keyword(self):
        if self._read_word():
            if self.s in self.falseValues:
                self._store_value(False)
            elif self.s in self.trueValues:
                self._store_value(True)
            elif self.s in self.nullValues:
                self._store_value(None)
            else:
                self._raise_error(JSONC_ERROR_UNKNOWN_KEYWORD, self.s)

    
    def _parse_value(self):
        if self._skip_whitespaces():
            c = self.data[self.i]
            self.s = ""
            self.escape = False
            self.n = 0
            self.divisor = 1
            if c in self.oneLineQuotes:
                self.quote = c
                self._next_char()
                self.func = self._parse_value_oneline_str
            elif c in self.multiLinesQuotes:
                self.quote = c
                self._next_char()
                self.func = self._parse_value_multilines_str
            elif _jsonc_is_digit(c):
                self.func = self._parse_value_number
            elif c == '{': 
                x = JsonCNode(self.node)
                self._store_value(x)
                self.node = x
                self.waitentry = True
                self._next_char()
                self.func = self._parse_node
            elif c == '[': 
                x = JsonCArray(self.node)
                self._store_value(x)
                self.node = x
                self.waitentry = True
                self._next_char()
                self.func = self._parse_array
            else:
                self.func = self._parse_value_keyword


    def _goto_parent(self):
        if self.node.parent is None:
            self.root = self.node
        self.node = self.node.parent
        if self.node is None:
            self.func = self._parse_end
        elif isinstance(self.node, JsonCArray):
            self.func = self._parse_array
        elif isinstance(self.node, JsonCNode):
            self.func = self._parse_node
        else:
            raise Exception("How did you get here ?!?")


    def _parse_node(self):
        if self._skip_whitespaces():
            c = self.data[self.i]
            if c == ',':
                if self.waitentry and not self.allowEmptyEntry:
                    self._raise_error(JSONC_ERROR_EMPTY_NODE_ENTRY)
                self.waitentry = True
            elif c == '}':
                self._goto_parent()
            else:
                if not self.waitentry:
                    self._raise_error(JSONC_ERROR_UNEXPECTED_NODE_SEP)
                self.func = self._parse_key
                self.waitentry = False
                return
            self._next_char()


    def _parse_array(self):
        if self._skip_whitespaces():
            c = self.data[self.i]
            if c == ',':
                if self.waitentry and not self.allowEmptyEntry:
                    self._raise_error(JSONC_ERROR_EMPTY_ARRAY_ENTRY)
                self.waitentry = True
            elif c == ']':
                self._goto_parent()
            else:
                if not self.waitentry:
                    self._raise_error(JSONC_ERROR_UNEXPECTED_ARRAY_SEP)
                self.func = self._parse_value
                self.waitentry = False
                return
            self._next_char()


    def _parse_end(self):
        if self._skip_whitespaces():
            self._raise_error(JSONC_ERROR_CHAR_AT_END)

    def finialize(self):
        self.data = self.lastc + "\0"
        self.i = 0
        self.m = 2
        self.func()
        if self.root is None:
            self.root = self.node


# Test
"""
parser = JsonCParser()
with open("test.jsonc", "r") as f:
    parser.parse(f.read())
    parser.finialize()
print("Result:")
print(parser.root.stringify())
"""
