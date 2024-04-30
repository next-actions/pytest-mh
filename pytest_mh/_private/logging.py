from __future__ import annotations

import logging
import textwrap
from logging.handlers import MemoryHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, Type

import colorama

from .misc import merge_dict, sanitize_path, should_collect_artifacts
from .types import MultihostOutcome

if TYPE_CHECKING:
    from .artifacts import MultihostArtifactsMode


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
        super().__init__(*args, **kwargs)

        self.allow_colors: bool = False
        self.log_path: str | None = None
        self.extra: dict[str, Any] = {}
        self.handler: logging.Handler | None = None
        self.artifacts_mode: MultihostArtifactsMode = "on-failure"
        self.artifacts_dir: Path = Path("")

    @classmethod
    def GetLogger(
        cls, *, loggercls: Type[MultihostLogger] | None = None, suffix: str | None = None
    ) -> MultihostLogger:
        """
        Returns the multihost logger.

        :param loggercls: Logger class, defaults to None (= cls).
        :type loggercls: Type[MultihostLogger] | None
        :param suffix: Logger name suffix, defaults to None.
        :type suffix: str | None
        :return: Logger.
        :rtype: MultihostLogger
        """
        name = "pytest_mh.logger"
        if suffix:
            name += f".{suffix}"

        if loggercls is None:
            loggercls = cls

        old_class = logging.getLoggerClass()

        logging.setLoggerClass(loggercls)
        logger = logging.getLogger(name)
        logging.setLoggerClass(old_class)

        if not isinstance(logger, loggercls):
            raise ValueError(f"logger must be instance of {loggercls.__name__}")

        return logger

    def setup(self, **kwargs) -> None:
        """
        Setup multihost logging facility.

        Colors are allowed if ``log_path`` is ``/dev/stdout`` or ``/dev/stderr``.

        :param log_path: Path to the log file.
        :type log_path: str
        """
        host_length = self._max_host_length(kwargs.get("confdict", {}))
        self.log_path = kwargs["log_path"]
        self.artifacts_mode = kwargs["artifacts_mode"]
        self.artifacts_dir = Path(kwargs["artifacts_dir"])
        self.allow_colors = self.log_path in ["/dev/stdout", "/dev/stderr"]
        self.handler = ManualMemoryHandler() if self.log_path is None else logging.FileHandler(self.log_path)

        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(
            logging.Formatter(f"%(levelname)-8s %(asctime)s %(host){host_length}s %(message)s", defaults={"host": ""})
        )

        self.addHandler(self.handler)
        self.addFilter(LogExtraDataFilter(logger=self, indent=34 + host_length))
        self.setLevel(logging.DEBUG)

    def subclass(self, cls: Type[MultihostLogger], suffix: str, **kwargs) -> MultihostLogger:
        logger: MultihostLogger = self.GetLogger(loggercls=cls, suffix=suffix)

        # Copy only level and filters, we don't want subloggers to have handlers
        logger.handlers = []
        logger.filters = list(self.filters)
        logger.level = self.level

        # Copy selected attributes
        logger.allow_colors = self.allow_colors
        logger.log_path = self.log_path
        logger.artifacts_mode = self.artifacts_mode
        logger.artifacts_dir = self.artifacts_dir
        logger.extra = dict(self.extra)

        logger.setup(**kwargs)

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

    def phase(self, phase: str) -> None:
        """
        Log current phase.

        :param phase: Phase name or description.
        :type phase: str
        """
        self.info(
            self.colorize(
                f"{phase}",
                colorama.Style.BRIGHT,
                colorama.Back.BLACK,
                colorama.Fore.WHITE,
            )
        )

    def debug(self, msg, *args, **kwargs):
        super().debug(msg, *args, **self._msgdata(kwargs))

    def info(self, msg, *args, **kwargs):
        super().info(msg, *args, **self._msgdata(kwargs))

    def warning(self, msg, *args, **kwargs):
        super().warning(msg, *args, **self._msgdata(kwargs))

    def warn(self, msg, *args, **kwargs):
        super().warn(msg, *args, **self._msgdata(kwargs))

    def error(self, msg, *args, **kwargs):
        super().error(msg, *args, **self._msgdata(kwargs))

    def exception(self, msg, *args, exc_info=True, **kwargs):
        super().exception(msg, *args, exc_info=exc_info, **self._msgdata(kwargs))

    def critical(self, msg, *args, **kwargs):
        super().critical(msg, *args, **self._msgdata(kwargs))

    def fatal(self, msg, *args, **kwargs):
        super().fatal(msg, *args, **self._msgdata(kwargs))

    def log(self, level, msg, *args, **kwargs):
        super().warning(level, msg, *args, **self._msgdata(kwargs))

    def split(self, path: str | Path) -> None:
        """
        Move current buffer to a file that will be written later.

        The files can be written by :meth:`write_files`

        :param path: Destination file path.
        :type path: str | Path
        """
        if isinstance(self.handler, ManualMemoryHandler):
            dest = self.artifacts_dir / sanitize_path(path)
            self.handler.split(str(dest))

    def flush(self, outcome: MultihostOutcome, path: str | Path | None = None) -> None:
        """
        Either write logger content to a file or clear it, depending on the
        outcome of the test or operation and selected artifacts mode.

        :param outcome: Test or operation outcome.
        :type outcome: MultihostOutcome
        :param path: Destination file path, if None :meth:`split` should be called first, defaults to None.
        :type path: str | Path | None
        """
        if path is not None:
            self.split(path)

        if isinstance(self.handler, ManualMemoryHandler):
            if should_collect_artifacts(self.artifacts_mode, outcome):
                self.handler.write_files()
            else:
                self.handler.clear_all()

    def _msgdata(self, kwargs) -> dict[str, Any]:
        if self.extra:
            return merge_dict(kwargs, {"extra": self.extra})

        return kwargs

    def _max_host_length(self, confict: dict) -> int:
        length = 0
        for domain in confict.get("domains", []):
            for host in domain.get("hosts", []):
                length = max(length, len(host.get("hostname", "")))

        return length


class MultihostHostLogger(MultihostLogger):
    """
    Logger for individual hosts.

    It includes hostname as ``host`` key in the message extra data.
    """

    def setup(self, **kwargs) -> None:
        self.extra["host"] = kwargs["hostname"]


class LogExtraDataFilter(logging.Filter):
    """
    :meta private:
    """

    def __init__(self, *args, logger: MultihostLogger, indent: int, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.indent: int = indent
        self.__logger: MultihostLogger = logger

    def dumps(self, o) -> str:
        if isinstance(o, dict):
            out = ""
            for key, value in o.items():
                value = str(value)
                out += "\n"
                out += textwrap.indent(f"{self.__logger.colorize(key, colorama.Fore.BLUE)}: {value}", " " * 2)

            return out

        if isinstance(o, (list, set, tuple)):
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
                    f"{self.__logger.colorize(key, colorama.Fore.MAGENTA)}: {self.dumps(value)}", " " * self.indent
                )

        return super().filter(record)


class ManualMemoryHandler(MemoryHandler):
    def __init__(self) -> None:
        super().__init__(capacity=0, flushLevel=0, target=None, flushOnClose=False)

        self.files: dict[str, list[logging.LogRecord]] = {}

    def shouldFlush(self, record: logging.LogRecord) -> bool:
        """
        This handler does not flush automatically.

        :param record: Log record. Unused.
        :type record: logging.LogRecord
        :return: Always return False.
        :rtype: bool
        """
        return False

    def split(self, path: str) -> None:
        """
        Move current buffer to a file that will be written later.

        The files can be written by :meth:`write_files`

        :param path: Destination file path.
        :type path: str
        """
        self.files[path] = self.buffer.copy()
        self.clear()

    def clear(self) -> None:
        """
        Clear current buffer without writing it anywhere.
        """
        self.buffer.clear()

    def clear_all(self) -> None:
        """
        Clear current buffer and buffered files without writing it anywhere.
        """
        self.clear()
        self.files.clear()

    def write_to_file(self, path: str | Path, content: list[logging.LogRecord] | None = None) -> None:
        """
        Write current buffer to a file and clear the buffer.

        :param path: Destination file path.
        :type path: str | Path
        :param content: Log records that will be written, current buffer if None, defaults to None.
        :type content: list[logging.LogRecord] | None
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        current_buffer = self.buffer
        self.buffer = content if content is not None else current_buffer

        try:
            handler = logging.FileHandler(path)
            handler.setLevel(self.level)
            handler.setFormatter(self.formatter)

            self.setTarget(handler)
            self.flush()
        finally:
            self.setTarget(None)
            self.buffer = current_buffer

    def write_files(self) -> None:
        """
        Write all buffered files to disk.
        """
        for path, content in self.files.items():
            self.write_to_file(path, content)

        self.files.clear()
