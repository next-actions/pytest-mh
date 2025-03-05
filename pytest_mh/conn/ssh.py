from __future__ import annotations

import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator, Self

import colorama as c
from pylibsshext.channel import Channel as LibsshChannel
from pylibsshext.errors import LibsshSessionException
from pylibsshext.session import Session as LibsshSession

from pytest_mh.conn import Process, ProcessLogLevel

from .._private.logging import MultihostLogger
from . import Connection, ConnectionError, ProcessError, ProcessInputBuffer, ProcessResult, ProcessTimeoutError, Shell

if TYPE_CHECKING:
    from .. import MultihostHost

__all__ = [
    "SSHClient",
    "SSHAuthenticationError",
    "SSHProcess",
    "SSHProcessError",
    "SSHProcessTimeoutError",
    "SSHInputBuffer",
    "SSHProcessResult",
]


class SSHInputBuffer(ProcessInputBuffer):
    """
    SSH Input Buffer.

    Allows to write into stdin of opened SSH channel.
    """

    def __init__(self, channel: LibsshChannel) -> None:
        """
        :param channel: Opened libssh channel.
        :type channel: LibsshChannel
        """
        self._channel: LibsshChannel = channel

    def write(self, data: str | bytes) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")

        self._channel.write(data)


class SSHOutputBuffer(Generator):
    """
    SSH Output Buffer.

    Reads from stdout or stderr from an opened SSH channel and makes each line
    of the data accessible through a generator.
    """

    def __init__(self, channel: LibsshChannel, stderr: bool):
        """
        :param channel: Opened libssh channel.
        :type channel: LibsshChannell
        :param stderr: Whether to read stdout or stderr.
        :type stderr: bool
        """
        self.channel: LibsshChannel = channel
        self.stderr: bool = stderr

        self.eof: bool = False
        self.chunk: str = ""
        self.lines: list[str] = []

    def _read(self) -> str:
        """
        Read available data.

        :rtype: str
        """
        chunk: bytes = b""
        while not self.eof:
            self.channel.poll(timeout=1000, stderr=self.stderr)
            new_chunk: bytes | None = self.channel.recv(stderr=self.stderr)

            if new_chunk is None:
                self.eof = True
            else:
                chunk += new_chunk

            try:
                out = chunk.decode("utf-8")
                return out
            except UnicodeDecodeError:
                # Error if we don't have anything more to read
                if self.eof:
                    raise

                # Otherwise concat with next chunk and see if we can decode it then
                continue

        return ""

    def finish(self) -> None:
        """
        Read all remaining data.
        """
        list(self)

    def read_once_into_buffer(self) -> None:
        """
        Read all data that are currently available and store it in the lines
        buffer.
        """
        self.chunk += self._read()

        while self.chunk:
            newline = self.chunk.find("\n")

            # Store a full line if it was already read
            if newline >= 0:
                line = self.chunk[:newline]
                self.lines.append(line)
                self.chunk = self.chunk[newline + 1 :]
                continue

            # Return remaining data if there is nothing else to read
            line = self.chunk
            self.lines.append(line)
            self.chunk = ""

    def send(self, value: Any):
        while True:
            if self.chunk:
                newline = self.chunk.find("\n")

                # Return a full line if it was already read
                if newline >= 0:
                    line = self.chunk[:newline]
                    self.lines.append(line)
                    self.chunk = self.chunk[newline + 1 :]
                    return line

                # Return remaining data if there is nothing else to read
                if self.eof and self.chunk:
                    line = self.chunk
                    self.lines.append(line)
                    self.chunk = ""
                    return line

            # Stop if we can not read anything more
            if self.eof and not self.chunk:
                raise StopIteration

            # Read more data
            self.chunk += self._read()

    def throw(self, typ, val=None, tb=None):
        super().throw(typ, val, tb)


class SSHProcessError(ProcessError):
    """
    SSH Process Error.
    """

    pass


class SSHProcessTimeoutError(ProcessTimeoutError):
    """
    SSH Process Timeout Error.
    """

    pass


class SSHProcessResult(ProcessResult[SSHProcessError]):
    """
    SSH Process result.
    """

    pass


class SSHProcess(Process[SSHProcessResult, SSHInputBuffer, SSHProcessTimeoutError]):
    """
    SSH Process manager.
    """

    def __init__(
        self,
        *,
        command: str,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | bytes | None = None,
        shell: Shell,
        logger: MultihostLogger,
        log_level: ProcessLogLevel,
        timeout: int,
        blocking_call: bool,
        client: SSHClient,
        conn: LibsshSession,
    ) -> None:
        """
        :param command: Command to execute.
        :type command: str
        :param cwd: Working directory, defaults to None
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | bytes | None, optional
        :param shell: Shell used to execute the command, defaults to None (use user's login shell)
        :type shell: str | None, optional
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param log_level: Log level.
        :type log_level: ProcessLogLevel
        :param timeout: Timeout in seconds, value ``0`` means that timeout is
            disabled.
        :type timeout: int
        :param blocking_call: Is this a blocking execution?
        :type blocking_call: bool
        :param client: SSH client.
        :type client: SSHClient
        :param conn: Connected SSH session.
        :type conn: LibsshSession
        """
        super().__init__(
            command=command,
            cwd=cwd,
            env=env,
            input=input,
            shell=shell,
            logger=logger,
            log_level=log_level,
            timeout=timeout,
            blocking_call=blocking_call,
            additional_log_data={
                "Host": client.host,
                "User": client.user,
            },
        )

        self.__conn: LibsshSession = conn
        self.__channel: LibsshChannel | None = None

        self.__stdout: SSHOutputBuffer | None = None
        self.__stderr: SSHOutputBuffer | None = None
        self.__stdin: SSHInputBuffer | None = None

    @property
    def in_progress(self) -> bool:
        return self.__channel is not None

    @property
    def stdout(self) -> Generator[str, None, None]:
        if not self.in_progress or self.__stdout is None:
            raise RuntimeError("Accessing stdout on a process that is not running.")

        return self.__stdout

    @property
    def stderr(self) -> Generator[str, None, None]:
        if not self.in_progress or self.__stderr is None:
            raise RuntimeError("Accessing stderr on a process that is not running.")

        return self.__stderr

    @property
    def stdin(self) -> SSHInputBuffer:
        if not self.in_progress or self.__stdin is None:
            raise RuntimeError("Accessing stdin on a process that is not running.")

        return self.__stdin

    def _run(self) -> None:
        """
        Execute the command.

        This is an internal method called by :meth:`run` after executing
        generic code.
        """
        self.__channel = self.__conn.new_channel()
        try:
            self.__channel.request_exec(self.full_command_line)
            self.__stdout = SSHOutputBuffer(self.__channel, stderr=False)
            self.__stderr = SSHOutputBuffer(self.__channel, stderr=True)
            self.__stdin = SSHInputBuffer(self.__channel)

            if self.input is not None:
                self.stdin.write(self.input)
        except Exception:
            self._close()
            raise

    def _wait(self) -> SSHProcessResult:
        """
        Wait for the command to finish.

        EOF is send to standard input to indicate that there will be no
        additional input data. Then it waits for the command to finish.

        This is an internal method called by :meth:`run` after executing
        generic code.

        :return: Command result.
        :rtype: SSHProcessResult
        """
        if self.__stdout is None or self.__stderr is None:
            raise RuntimeError("Calling wait on process that has not yet started.")

        try:
            # Notify the program that there will be no more input
            self.send_eof()

            # Wait for the program to finish and get the exit code.
            code = self._wait_for_rc()

            # Read remaining output, this will finish the output generator and append
            # remaining lines to self.__stdout and self.__stderr buffers.
            self.__stdout.finish()
            self.__stderr.finish()

            error = SSHProcessError(
                code, self.id, self.command, self.cwd, self.env, self.input, self.__stdout.lines, self.__stderr.lines
            )

            result = SSHProcessResult(code, self.__stdout.lines, self.__stderr.lines, error)
        except TimeoutError as e:
            self.__stdout.read_once_into_buffer()
            self.__stderr.read_once_into_buffer()
            raise SSHProcessTimeoutError(
                e.args[0],
                self.id,
                self.command,
                self.cwd,
                self.env,
                self.input,
                self.__stdout.lines,
                self.__stderr.lines,
            )
        finally:
            self._close()

        return result

    def send_eof(self) -> None:
        if self.__channel is None:
            raise RuntimeError("Calling send_eof on process that is not running.")

        self.__channel.send_eof()

    def send_signal(self, sig: signal.Signals) -> None:
        if self.__channel is None:
            raise RuntimeError("Calling send_signal on process that is not running.")

        self.__channel.send_signal(sig)

    def _close(self) -> None:
        if self.__channel is None:
            return

        self.__channel.close()
        self.__channel = None
        self.__stdout = None
        self.__stderr = None
        self.__stdin = None

    def _wait_for_rc(self) -> int:
        if self.__channel is None:
            raise RuntimeError("Calling _wait_for_rc on process that is not running.")

        rc = -1
        while rc == -1:
            rc = self.__channel.get_channel_exit_status()
            if rc == -1:
                self.__channel.poll(timeout=5)

        return rc


class SSHAuthenticationError(ConnectionError):
    """
    Unable to authenticate over SSH.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        message: str,
    ) -> None:
        super().__init__(f'Unable to authenticate as "{user}" at {host}:{port} over SSH: {message}')


class SSHClient(Connection[SSHProcess, SSHProcessResult]):
    """
    Interactive SSH client.
    """

    def __init__(
        self,
        host: str,
        *,
        user: str,
        password: str | None = None,
        private_key_path: str | Path | None = None,
        private_key_password: str | None = None,
        port: int = 22,
        shell: Shell,
        logger: MultihostLogger,
        timeout: int = 300,
    ) -> None:
        """
        :param host: Host name to connect to.
        :type host: str
        :param user: Username to authenticate.
        :type user: str
        :param password: Password for authentication, defaults to ``None``.
        :type password: str | None
        :param private_key_path: Path to the private key for authentication, defaults to ``None``.
        :type private_key_path: str | Path | None
        :param private_key_password: Password to unlock the private key, defaults to ``None``.
        :type private_key_password: str | None
        :param port: SSH port, defaults to 22
        :type port: int, optional
        :param shell: User shell used to run commands, defaults to SSHBashProcess
        :type shell: str, optional
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param timeout: Timeout in seconds (defaults to 300), value
            ``0`` means that timeout is disabled.
        :type timeout: int
        """
        super().__init__(shell=shell, logger=logger, timeout=timeout)

        if password is None and private_key_path is None:
            raise ValueError("At least one authentication mechanism has to be set.")

        self.host: str = host
        self.user: str = user
        self.port: int = port

        self.password: str | None = password
        self.private_key: bytes | None = None
        self.private_key_password: bytes | None = None
        self.private_key, self.private_key_password = self._read_private_key(private_key_path, private_key_password)

        # Timeout is maximum number of seconds that operation can block, after
        # then it returns error and we need to retry. It is necessary to set,
        # since Python will not deliver signal if the code is blocked in C
        # library. The signal is deliver only after we get back to the Python
        # code.
        self.__conn: LibsshSession = LibsshSession()

    def _read_private_key(
        self,
        path: str | Path | None = None,
        password: str | None = None,
    ) -> tuple[bytes | None, bytes | None]:
        private_key: bytes | None = None
        private_key_password: bytes | None = None

        if path is not None:
            with open(path, "rb") as f:
                private_key = f.read()

        if password is not None:
            private_key_password = password.encode("utf-8")

        return private_key, private_key_password

    @property
    def requested_auth_methods(self) -> list[str]:
        """
        :return: List of authentication methods requested by the caller.
        :rtype: list[str]
        """
        methods = []

        if self.password is not None:
            methods.append("password")

        if self.private_key is not None:
            methods.append("private key")

        return methods

    @property
    def connected(self) -> bool:
        return bool(self.__conn.is_connected)

    def connect(self) -> None:
        """
        Connect to the host.

        :raises SSHAuthenticationError: If user fails to authenticate.
        """
        if self.connected:
            return

        self.logger.info(
            self.logger.colorize("Opening SSH connection to ", c.Style.BRIGHT)
            + self.logger.colorize(self.host, c.Fore.BLUE, c.Style.BRIGHT)
            + self.logger.colorize(f" using {'/'.join(self.requested_auth_methods)}", c.Style.BRIGHT)
        )

        try:
            self.__conn.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                private_key=self.private_key,
                private_key_password=self.private_key_password,
                port=self.port,
                host_key_checking=False,
            )
            self.__conn.set_ssh_options("timeout", 1)
        except LibsshSessionException as e:
            raise SSHAuthenticationError(self.host, self.port, self.user, e.message)

    def disconnect(self) -> None:
        self.logger.info(
            self.logger.colorize("Closing SSH connection to ", c.Style.BRIGHT)
            + self.logger.colorize(self.host, c.Fore.BLUE, c.Style.BRIGHT)
        )

        self.__conn.disconnect()

    def create_process(
        self,
        *,
        command: str,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | bytes | None = None,
        log_level: ProcessLogLevel,
        blocking_call: bool,
    ) -> SSHProcess:
        return SSHProcess(
            command=command,
            cwd=cwd,
            env=env,
            input=input,
            shell=self.shell,
            logger=self.logger,
            log_level=log_level,
            timeout=self.timeout,
            blocking_call=blocking_call,
            client=self,
            conn=self.__conn,
        )

    @classmethod
    def from_confdict(cls, host: MultihostHost, confdict: dict[str, Any]) -> Self:
        ssh_host: str = confdict.get("host", host.hostname)
        ssh_port: int = int(confdict.get("port", 22))
        ssh_username: str = confdict.get("username", "root")
        ssh_password: str | None = confdict.get("password", None)
        ssh_private_key: str | None = confdict.get("private_key", None)
        ssh_private_key_password: str | None = confdict.get("private_key_password", None)
        timeout: int = confdict.get("timeout", 300)

        if ssh_password is None and ssh_private_key is None:
            ssh_password = "Secret123"

        return cls(
            host=ssh_host,
            user=ssh_username,
            password=ssh_password,
            private_key_path=ssh_private_key,
            private_key_password=ssh_private_key_password,
            port=ssh_port,
            logger=host.logger,
            shell=host.shell,
            timeout=timeout,
        )
