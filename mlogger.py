import sys
import os
from datetime import datetime, timedelta
import threading
import time


def _are_ansi_color_supported():
    plat = sys.platform
    supported_platform = plat != 'Pocket PC' and (plat != 'win32' or 'ANSICON' in os.environ)
    # isatty is not always implemented, #6223.
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty


class _CustomWriteIO:
    def __init__(self, write_func):
        self.write_func = write_func
    def write(self, data):
        self.write_func(data)
        return len(data)
    def flush(self):
        pass


def encode(s):
    return s.encode('utf-8', errors='ignore')


_base_stdout = sys.__stdout__
_base_stderr = sys.__stderr__

# Currently no good way to do
_base_stdout._errors = "backslashreplace"
_base_stderr._errors = "backslashreplace"


# Linux color codes

fg_darkblack    = ""
fg_darkred      = ""
fg_darkgreen    = ""
fg_darkyellow   = ""
fg_darkblue     = ""
fg_darkmagenta  = ""
fg_darkcyan     = ""
fg_darkwhite    = ""

fg_black        = ""
fg_red          = ""
fg_green        = ""
fg_gold         = ""
fg_blue         = ""
fg_purple       = ""
fg_cyan         = ""
fg_lightgrey    = ""

fg_lightblack   = ""
fg_lightred     = ""
fg_lightgreen   = ""
fg_lightyellow  = ""
fg_lightblue    = ""
fg_lightmagenta = ""
fg_lightcyan    = ""
fg_lightwhite   = ""

fg_darkgrey     = ""
fg_pink         = ""
fg_lime         = ""
fg_yellow       = ""
fg_magenta      = ""
fg_white        = ""
fg_grey         = ""

darkblack       = ""
darkred         = ""
darkgreen       = ""
darkyellow      = ""
darkblue        = ""
darkmagenta     = ""
darkcyan        = ""
darkwhite       = ""

black           = ""
red             = ""
green           = ""
gold            = ""
blue            = ""
purple          = ""
cyan            = ""
lightgrey       = ""

lightblack      = ""
lightred        = ""
lightgreen      = ""
lightyellow     = ""
lightblue       = ""
lightmagenta    = ""
lightcyan       = ""
lightwhite      = ""

darkgrey        = ""
pink            = ""
lime            = ""
yellow          = ""
magenta         = ""
white           = ""
grey            = ""

bg_darkblack    = ""
bg_darkred      = ""
bg_darkgreen    = ""
bg_darkyellow   = ""
bg_darkblue     = ""
bg_darkmagenta  = ""
bg_darkcyan     = ""
bg_darkwhite    = ""

bg_black        = ""
bg_red          = ""
bg_green        = ""
bg_gold         = ""
bg_blue         = ""
bg_purple       = ""
bg_cyan         = ""
bg_lightgrey    = ""

bg_lightblack   = ""
bg_lightred     = ""
bg_lightgreen   = ""
bg_lightyellow  = ""
bg_lightblue    = ""
bg_lightmagenta = ""
bg_lightcyan    = ""
bg_lightwhite   = ""

bg_darkgrey     = ""
bg_pink         = ""
bg_lime         = ""
bg_yellow       = ""
bg_magenta      = ""
bg_white        = ""
bg_grey         = ""

reset_all       = ""
reset_bright    = ""
reset_dim       = ""
reset_underline = ""
reset_blink     = ""
reset_reverse   = ""
reset_hidden    = ""

reset           = ""

bright          = ""
dim             = ""
underline       = ""
blink           = ""
reverse         = ""
hidden          = ""


if True or os.name == 'posix':
    fg_black        = '\x1b[30m'
    fg_red          = '\x1b[31m'
    fg_green        = '\x1b[32m'
    fg_yellow       = '\x1b[33m'
    fg_blue         = '\x1b[34m'
    fg_magenta      = '\x1b[35m'
    fg_cyan         = '\x1b[36m'
    fg_white        = '\x1b[37m'

    fg_lightblack   = '\x1b[90m'
    fg_lightred     = '\x1b[91m'
    fg_lightgreen   = '\x1b[92m'
    fg_lightyellow  = '\x1b[93m'
    fg_lightblue    = '\x1b[94m'
    fg_lightmagenta = '\x1b[95m'
    fg_lightcyan    = '\x1b[96m'
    fg_lightwhite   = '\x1b[97m'

    bg_black        = '\x1b[40m'
    bg_red          = '\x1b[41m'
    bg_green        = '\x1b[42m'
    bg_yellow       = '\x1b[43m'
    bg_blue         = '\x1b[44m'
    bg_magenta      = '\x1b[45m'
    bg_cyan         = '\x1b[46m'
    bg_white        = '\x1b[47m'

    bg_lightblack   = '\x1b[100m'
    bg_lightred     = '\x1b[101m'
    bg_lightgreen   = '\x1b[102m'
    bg_lightyellow  = '\x1b[103m'
    bg_lightblue    = '\x1b[104m'
    bg_lightmagenta = '\x1b[105m'
    bg_lightcyan    = '\x1b[106m'
    bg_lightwhite   = '\x1b[107m'

    reset           = '\x1b[0m'

    bright          = '\x1b[1m'
    dim             = '\x1b[2m'
    underline       = '\x1b[4m'
    blink           = '\x1b[5m'
    reverse         = '\x1b[7m' # Invert the bg and fg colors
    hidden          = '\x1b[8m'



LVL_UNKNOW  = 0
LVL_DEBUG   = 1
LVL_INFO    = 2
LVL_WARNING = 3
LVL_ERROR   = 4
LVL_FATAL   = 5



class Logger:
    def __init__(self) -> None:
        # Rotation filename is : FILENAME_PREFIX + FILENAME_FORMAT + <counter> + FILENAME_SUFFIX
        self._rotation_enable = False
        self._rotation_interval = timedelta(days = 1) # Default to 1 day interval
        self._rotation_prefix = ""
        self._rotation_format = "%Y-%m-%d-"
        self._rotation_suffix = ".log"
        self._rotation_folder = "logs/"
        self._rotation_latest = "latest.log"
        self._rotation_last = None # Datetime of the last rotation

        self._strftime_format = "%d-%m-%Y %H:%M:%S"

        self._line_level = None

        self._file = None
        self._allow_color = _are_ansi_color_supported()

        self._file_close_thr = threading.Thread(target=self._wait_close_file)
        self._file_close_thr.start()

        """
        # Shortcuts
        self.dbg    = self.debug
        self.inf    = self.info
        self.warn   = self.warning
        self.err    = self.error
        self.critic = self.fatal
        """

    def useAsDefault(self):
        sys.stdout = _CustomWriteIO(self._io_info)
        sys.stderr = _CustomWriteIO(self._io_error)

    def _io_info(self, data):
        self._write(LVL_INFO, "Info", data, fg_lightblue, fg_lightwhite, _base_stdout, self._line_level is None)

    def _io_error(self, data):
        self._write(LVL_ERROR, "Error", data, fg_red, fg_lightred, _base_stderr, self._line_level is None)

    def openFile(self, filename : str, append : bool =True) -> None:
        pdir = os.path.dirname(filename)
        if pdir and not os.path.isdir(pdir):
            os.makedirs(pdir)
        self._file = open(filename, 'ab' if append else 'wb')

    def closeFile(self) -> None:
        if self._file is not None:
            if not self._file.closed:
                self._file.close()
            self._file = None

    def allowColor(self, allow : bool) -> None:
        self._allow_color = allow

    def setTimeFormat(self, format : str) -> None:
        self._strftime_format = format

    def enableRotation(self, enable : bool) -> None:
        self._rotation_enable = enable

    def _is_filename_similar(self, prefix : str, suffix : str, length : int, filename : str) -> bool:
        return len(filename) == length and filename.startswith(prefix) and filename.endswith(suffix)

    def _get_next_rotation_filename(self) -> None:
        base_filename_prefix = self._rotation_prefix + datetime.now().strftime(self._rotation_format)
        base_filename = base_filename_prefix + "%03d" + self._rotation_suffix
        base_filename_len = len(base_filename) - 4 + 3

        if not os.path.isdir(self._rotation_folder):
            return base_filename % 0

        similar_filenames = set()

        for filename in os.listdir(self._rotation_folder):
            if os.path.isfile(os.path.join(self._rotation_folder, filename)):
                if self._is_filename_similar(base_filename_prefix, self._rotation_suffix, base_filename_len, filename):
                    similar_filenames.add(filename)

        for count in range(0, 1000):
            filename = base_filename % count
            if filename not in similar_filenames:
                return filename
        
        # Can't find proper filename
        return None

    def setRotationInterval(self, interval : timedelta) -> None:
        self._rotation_interval = interval

    def setRotationFileName(self, prefix : str, format : str, suffix : str) -> None:
        self._rotation_prefix = prefix
        self._rotation_format = format
        self._rotation_suffix = suffix

    def setRotationFolder(self, folder : str) -> None:
        self._rotation_folder = folder

    def setRotationLatestFileName(self, filename : str) -> None:
        self._rotation_latest = filename

    def createRotationLatestFile(self) -> None:
        self.closeFile()
        self.openFile(self._rotation_latest, False)

    def doRotation(self) -> None:
        if os.path.isfile(self._rotation_latest):
            filename = self._get_next_rotation_filename()
            if filename is None:
                self.closeFile()
                return
            if not os.path.isdir(self._rotation_folder):
                os.makedirs(self._rotation_folder)
            os.rename(self._rotation_latest, os.path.join(self._rotation_folder, filename))
        self.createRotationLatestFile()

    def checkRotation(self) -> None:
        if self._rotation_enable:
                if self._rotation_last is None or datetime.now() >= self._rotation_next:
                    x = (datetime.now() - datetime.min) // self._rotation_interval
                    self._rotation_next = (x + 1) * self._rotation_interval + datetime.min
                    self.doRotation()


    def _wait_close_file(self) -> None:
        while True:
            if not threading.main_thread().is_alive() and threading.active_count() <= 2:
                self.closeFile()
                break
            time.sleep(.25)

    def _format(self, lvl : int, t : str, s : str, colored : bool, t_color : str, s_color : str, set_line_level : bool) -> str:
        if colored:
            prefix = fg_lightblack + "[" + fg_white + datetime.now().strftime(self._strftime_format) + fg_lightblack + "] " + t_color + t + ": " + s_color
        else:
            prefix = "[" + datetime.now().strftime(self._strftime_format) + "] " + t + ": "

        lines = s.split('\n')

        if len(lines) == 0:
            return ""

        out = None
        if self._line_level is None:
            if lines[0]:
                out = prefix + lines[0]
            else:
                out = ""
        else:
            if lvl == self._line_level:
                out = lines[0]
            else:
                if lines[0]:
                    out = "\n" + prefix + lines[0]
                else:
                    out = "\n"

        for i in range(1, len(lines)):
            line = lines[i]
            out += "\n"
            if line != "":
                out += prefix
                out += line
            i += 1
        
        if set_line_level:
            self._line_level = lvl if lines[-1] else None

        return out
        
    def _merge_args(self, args : list, sep=' ') -> str:
        out = ""
        first = True
        for a in args:
            if first:
                first = False
            else:
                out += sep
            out += str(a)
        return out

    def _write(self, lvl : int, t : str, s : str, t_color : str, s_color : str, ioptr, flush : bool) -> None:
        if self._file is not None:
            self._file.write( encode( self._format(lvl, t, s, False, None, None, False) ) )
            if flush: self._file.flush()
        ioptr.write( self._format(lvl, t, s, self._allow_color, t_color, s_color, True) )
        if flush: ioptr.flush()


    def debug(self, *args, sep : str = ' ', end : str = '\n', flush : bool = False) -> None:
        self._write(LVL_DEBUG, "Debug", self._merge_args(args,sep)+end, fg_lightblack, fg_white, _base_stdout, self._line_level is None or flush)

    def info(self, *args, sep : str = ' ', end : str = '\n', flush : bool = False) -> None:
        self._write(LVL_INFO, "Info", self._merge_args(args,sep)+end, fg_lightblue, fg_lightwhite, _base_stdout, self._line_level is None or flush)

    def warning(self, *args, sep : str = ' ', end : str = '\n', flush : bool = False) -> None:
        self._write(LVL_WARNING, "Warning", self._merge_args(args,sep)+end, fg_yellow, fg_lightyellow, _base_stdout, self._line_level is None or flush)

    def error(self, *args, sep : str = ' ', end : str = '\n', flush : bool = False) -> None:
        self._write(LVL_ERROR, "Error", self._merge_args(args,sep)+end, fg_red, fg_lightred, _base_stderr, self._line_level is None or flush)

    def fatal(self, *args, sep : str = ' ', end : str = '\n', flush : bool = False) -> None:
        self._write(LVL_FATAL, "Fatal", self._merge_args(args,sep)+end, fg_red, fg_red, _base_stderr, self._line_level is None or flush)



# Test code
"""
logger = Logger()
logger.useAsDefault()
logger.openFile("log.txt")
logger.debug("test")
logger.info("test1")
logger.info("test2")
logger.info("test3")
logger.warning("test")
logger.error("test")
logger.fatal("test")
print("test")
print("test", file=sys.stderr)
a = 10 / 0
"""
