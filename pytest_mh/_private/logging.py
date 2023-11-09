from __future__ import annotations

import logging
import textwrap
from logging.handlers import MemoryHandler
from pathlib import Path
from typing import Any

import colorama


class MultihostLogger(logging.Logger):
    """
    Multihost logger class.

    It extends the standard logger with additional :meth:`colorize` method that
    can be used to put some colors into the log message.

    It also allows to log extra data, that are printed in a formatted way
    together with the message.

    .. code-block:: python

        logger.info(
            'Main message'',
            extra={'data': {
                'Field1': 'value1',
                'Field2': 'value2',
                ...
            }}
        )
    """

    def __init__(self, *args, **kwargs) -> None:
        """ """
        super().__init__(*args, **kwargs)

        self.allow_colors: bool = False
        self.log_path: str | None = None
        self.handler: logging.Handler | None = None

    def setup(self, log_path: str) -> None:
        """
        Setup multihost logging facility.

        Colors are allowed if ``log_path`` is ``/dev/stdout`` or ``/dev/stderr``.

        :param log_path: Path to the log file.
        :type log_path: str
        :return: Logger.
        :rtype: MultihostLogger
        """
        self.log_path = log_path
        self.allow_colors = self.log_path in ["/dev/stdout", "/dev/stderr"]
        self.handler = ManualMemoryHandler() if self.log_path is None else logging.FileHandler(self.log_path)

        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter("%(levelname)-8s %(asctime)s %(message)s"))

        self.addHandler(self.handler)
        self.addFilter(LogExtraDataFilter(logger=self))
        self.setLevel(logging.DEBUG)

    @classmethod
    def GetLogger(cls) -> MultihostLogger:
        """
        Returns the multihost logger.

        :return: Logger.
        :rtype: MultihostLogger
        """
        old_class = logging.getLoggerClass()

        logging.setLoggerClass(cls)
        logger = logging.getLogger("pytest_mh.logger")
        logging.setLoggerClass(old_class)

        if not isinstance(logger, cls):
            raise ValueError("logger must be instance of MultihostLogger")

        return logger

    def clear(self) -> None:
        """
        Clear current log records buffer without writing it anywhere.
        """
        if isinstance(self.handler, ManualMemoryHandler):
            self.handler.clear()

    def write_to_file(self, path: str) -> None:
        """
        Write current log records buffer to a file and clear the buffer.

        :param path: Destination file path.
        :type path: str
        """
        if isinstance(self.handler, ManualMemoryHandler):
            self.handler.write_to_file(path)

    def colorize(self, text: str | Any, *colors: str) -> str:
        """
        Make the ``text`` colored with ANSI colors.

        :param text: Text to format. ``str(text)`` is called on the parameter.
        :type text: str | Any
        :param \\*colors: Colors to apply on the text.
        :type \\*colors: colorama.Fore | colorama.Back | colorama.Style
        :return: Text with colors, if colors are allowed. Unchanged text otherwise.
        :rtype: str
        """
        if not self.allow_colors:
            return str(text)

        return "".join(colors) + str(text) + colorama.Style.RESET_ALL


class LogExtraDataFilter(logging.Filter):
    """
    :meta private:
    """

    def __init__(self, *args, logger: MultihostLogger, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__logger = logger

    def dumps(self, o) -> str:
        if isinstance(o, dict):
            out = ""
            for key, value in o.items():
                value = str(value)
                out += "\n"
                out += textwrap.indent(f"{self.__logger.colorize(key, colorama.Fore.BLUE)}: {value}", " " * 2)

            return out

        if isinstance(o, list):
            out = ""
            for value in o:
                out += "\n- " + str(value)

            return out

        value = str(o)
        if "\n" not in value:
            return value

        return "|\n" + textwrap.indent(value, " " * 2)

    def filter(self, record):
        if hasattr(record, "data"):
            for key, value in record.data.items():
                record.msg += "\n"
                record.msg += textwrap.indent(
                    f"{self.__logger.colorize(key, colorama.Fore.MAGENTA)}: {self.dumps(value)}", " " * 33
                )

        return super().filter(record)


class ManualMemoryHandler(MemoryHandler):
    def __init__(self) -> None:
        super().__init__(capacity=0, flushLevel=0, target=None, flushOnClose=False)

    def shouldFlush(self, record: logging.LogRecord) -> bool:
        """
        This handler does not flush automatically.

        :param record: Log record. Unused.
        :type record: logging.LogRecord
        :return: Always return False.
        :rtype: bool
        """
        return False

    def clear(self) -> None:
        """
        Clear current buffer without writing it anywhere.
        """
        self.buffer.clear()

    def write_to_file(self, path: str) -> None:
        """
        Write current buffer to a file and clear the buffer.

        :param path: Destination file path.
        :type path: str
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(path)
        handler.setLevel(self.level)
        handler.setFormatter(self.formatter)

        self.setTarget(handler)
        self.flush()
        self.setTarget(None)
