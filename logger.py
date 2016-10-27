import datetime
import logging
import logging.handlers
import os

from colorlog import ColoredFormatter


class DateFormatter(logging.Formatter):
    converter = datetime.datetime.fromtimestamp

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)

        if datefmt:
            s = ct.strftime(datefmt)
        else:
            t = ct.strftime("%Y-%m-%d %H:%M:%S")
            s = "%s.%03d" % (t, record.msecs)

        return s


class Logger(object):
    def __init__(self):
        self.logger = None
        self.log_level = logging.DEBUG

    def get(self):
        fmt = '%(levelname)-8s %(message)s'
        reset = False

        log_colors = {
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red',
        }

        formatter = ColoredFormatter(fmt, datefmt=None, log_colors=log_colors, reset=reset)

        if not self.logger:
            self.logger = logging.getLogger()
            self.console_handler = logging.StreamHandler()

            # default dsn
            current_path = os.path.dirname(os.path.abspath(__file__))

        self.console_handler.setFormatter(formatter)
        self.logger.removeHandler(self.console_handler)
        self.logger.addHandler(self.console_handler)

        self.logger.setLevel(self.log_level)
        return self.logger

log = Logger()
logger = log.get()
