from __future__ import annotations

import logging
import textwrap
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

    @classmethod
    def Setup(cls, log_path: str) -> MultihostLogger:
        """
        Setup multihost logging facility.

        Colors are allowed if ``log_path`` is ``/dev/stdout`` or ``/dev/stderr``.

        :param log_path: Path to the log file.
        :type log_path: str
        :return: Logger.
        :rtype: MultihostLogger
        """
        logger = cls.GetLogger()

        if log_path is None:
            return logger

        if log_path == "/dev/stdout" or log_path == "/dev/stderr":
            logger.allow_colors = True

        handler = logging.FileHandler(log_path)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(asctime)s %(message)s"))

        logger.addHandler(handler)
        logger.addFilter(LogExtraDataFilter(logger=logger))
        logger.setLevel(logging.DEBUG)

        return logger

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
