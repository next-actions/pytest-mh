from __future__ import annotations

import itertools
import os
import shlex
import textwrap
from enum import Enum, auto
from typing import Any, Generator, NoReturn, Self, Type

import colorama as c
from pylibsshext.channel import Channel as LibsshChannel
from pylibsshext.errors import LibsshSessionException
from pylibsshext.session import Session as LibsshSession

from ._private.logging import MultihostLogger


class SSHLog(Enum):
    """
    SSH command log level.
    """

    Silent = auto()
    """
    No log messages are produced.
    """

    Short = auto()
    """
    Command execution and return code is logged. Its output is omitted.
    """

    Full = auto()
    """
    Command execution, its return code and output is logged.
    """

    Error = auto()
    """
    Only log the command and its result on non-zero exit code.
    """


class SSHInputBuffer(object):
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

    def write(self, data: str) -> None:
        """
        Write data to stdin.

        :param data: Data to write.
        :type data: str
        """
        self._channel.write(data.encode("utf-8"))


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
        while not self.eof:
            self.channel.poll(timeout=1000, stderr=self.stderr)
            chunk = self.channel.recv(stderr=self.stderr)
            if chunk is None:
                self.eof = True
                return ""

            if not chunk:
                continue

            return chunk.decode("utf-8")

        return ""

    def finish(self) -> None:
        """
        Read all remaining data.
        """
        list(self)

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


class SSHProcess(object):
    """
    SSH Process.

    .. note::

        You should not create instances of this class yourself. Use method
        :meth:`SSHClient.run`, :meth:`SSHClient.exec`,
        :meth:`SSHClient.async_run` and :meth:`SSHClient.async_exec` from
        :class:`SSHClient` to execute a command over SSH.
    """

    __genid = itertools.count()

    def __init__(
        self,
        *,
        command: str,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | None = None,
        shell: str | None = None,
        client: SSHClient,
        conn: LibsshSession,
        read_timeout: float,
        logger: MultihostLogger,
        log_level: SSHLog,
        sync_exec: bool,
    ) -> None:
        """
        :param command: Command to execute.
        :type command: str
        :param cwd: Working directory, defaults to None
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | None, optional
        :param shell: Shell used to execute the command, defaults to None (use user's login shell)
        :type shell: str | None, optional
        :param client: SSH client.
        :type client: SSHClient
        :param conn: Connected SSH session.
        :type conn: LibsshSession
        :param read_timeout: Timeout in seconds, how long should the client wait
            for output, defaults to 30 seconds
        :type read_timeout: float
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param log_level: Log level.
        :type log_level: SSHLog
        :param sync_exec: Is this a blocking execution?
        :type sync_exec: bool
        """
        self.__client: SSHClient = client
        self.__conn: LibsshSession = conn
        self.__channel: LibsshChannel | None = None

        self.__logger: MultihostLogger = logger
        self.__log_level: SSHLog = self._get_log_level(log_level)
        self.__sync_exec: bool = sync_exec

        self.id: int = next(self.__genid) + 1
        self.command: str = textwrap.dedent(command).strip()
        self.cwd: str | None = cwd
        self.env: dict[str, Any] = env if env is not None else {}
        self.input: str | None = input
        self.shell: str | None = shell
        self.read_timeout: float = read_timeout

        self.__stdout: SSHOutputBuffer | None = None
        self.__stderr: SSHOutputBuffer | None = None
        self.__stdin: SSHInputBuffer | None = None

    @property
    def in_progress(self) -> bool:
        """
        :return: True if a command is already started and in progress.
        :rtype: bool
        """
        return self.__channel is not None

    @property
    def stdout(self) -> Generator[str, None, None]:
        """
        Standard output, returns generator which yields output line by line.

        .. code-block:: python

            # Read single line, this will block until there is a line to read or read_timeout is reached
            line = next(process.stdout)

            # Read all lines, this will block until EOF or read_timeout is reached
            lines = list(process.stdout)

            # Iterate over all lines
            for line in process.stdout:
                pass

        :raises RuntimeError: If the process is not running.
        :return: Standard output generator.
        :rtype: Generator[str, None, None]
        """
        if not self.in_progress or self.__stdout is None:
            raise RuntimeError("Accessing stdout on a process that is not running.")

        return self.__stdout

    @property
    def stderr(self) -> Generator[str, None, None]:
        """
        Standard error output, returns generator which yields error output line by line.

        .. code-block:: python

            # Read single line, this will block until there is a line to read or read_timeout is reached
            line = next(process.stderr)

            # Read all lines, this will block until EOF or read_timeout is reached
            lines = list(process.stderr)

            # Iterate over all lines
            for line in process.stderr:
                pass

        :raises RuntimeError: If the process is not running.
        :return: Standard error output generator.
        :rtype: Generator[str, None, None]
        """
        if not self.in_progress or self.__stderr is None:
            raise RuntimeError("Accessing stderr on a process that is not running.")

        return self.__stderr

    @property
    def stdin(self) -> SSHInputBuffer:
        """
        Command's standard input.

        .. code-block:: python

            # Write data
            process.stdin.write('Hello World')

            # Send EOF to indicate that there will be no more input data.
            process.send_eof()

        :raises RuntimeError: If the process is not running.
        :return: Standard input file.
        :rtype: SSHInputBuffer
        """
        if not self.in_progress or self.__stdin is None:
            raise RuntimeError("Accessing stdin on a process that is not running.")

        return self.__stdin

    def run(self) -> Self:
        """
        Execute the command.

        :return: Self.
        :rtype: SSHProcess
        """
        complete_command = self._escape_command(self._build_complete_command(self.command, cwd=self.cwd, env=self.env))

        if self.__log_level in (SSHLog.Short, SSHLog.Full):
            self.__logger.info(
                self.__msg_execution(),
                extra={
                    "data": {
                        "Host": self.__client.host,
                        "Shell": self.shell,
                        "User": self.__client.user,
                        "Command": self.command,
                        "Input": self.input,
                        "Working directory": self.cwd,
                        "Extra environment": self.env,
                    }
                },
            )

        self.__channel = self.__conn.new_channel()
        try:
            self.__channel.request_exec(f"{self.shell} '{complete_command}'")
            self.__stdout = SSHOutputBuffer(self.__channel, stderr=False)
            self.__stderr = SSHOutputBuffer(self.__channel, stderr=True)
            self.__stdin = SSHInputBuffer(self.__channel)

            if self.input is not None:
                self.stdin.write(self.input)
        except Exception:
            self._close()
            raise

        return self

    def wait(self, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Wait for the command to finish.

        EOF is send to standard input to indicate that there will be no
        additional input data. Then it waits for the command to finish.

        :param raise_on_error: If True, :class:`SSHProcessError` is raised on non-zero return code, defaults to True
        :type raise_on_error: bool, optional
        :raises SSHProcessError: If ``raise_on_error`` is True and the command exited with non-zero return code.
        :return: Command result.
        :rtype: SSHProcessResult
        """
        if not self.in_progress or self.__stdout is None or self.__stderr is None:
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

            result = SSHProcessResult(code, self.__stdout.lines, self.__stderr.lines)
            result._error = SSHProcessError(
                self.id, self.command, result.rc, self.cwd, self.env, self.input, result.stdout, result.stderr
            )
        finally:
            self._close()

        if self.__log_level == SSHLog.Error and result.rc != 0:
            self.__logger.error(
                self.__msg_completed_async(result.rc),
                extra={
                    "data": {
                        "Host": self.__client.host,
                        "User": self.__client.user,
                        "Command": self.command,
                        "Input": self.input,
                        "Working directory": self.cwd,
                        "Extra environment": self.env,
                        "Output": result.stdout,
                        "Error output": result.stderr,
                    }
                },
            )

        if self.__sync_exec:
            match self.__log_level:
                case SSHLog.Short:
                    self.__logger.info(self.__msg_completed_sync(result.rc))
                case SSHLog.Full:
                    self.__logger.info(
                        self.__msg_completed_sync(result.rc),
                        extra={
                            "data": {
                                "Output": result.stdout,
                                "Error output": result.stderr,
                            }
                        },
                    )
                case _:
                    pass
        else:
            match self.__log_level:
                case SSHLog.Short:
                    self.__logger.info(
                        self.__msg_completed_async(result.rc),
                        extra={
                            "data": {
                                "Host": self.__client.host,
                                "User": self.__client.user,
                                "Command": self.command,
                                "Input": self.input,
                                "Working directory": self.cwd,
                                "Extra environment": self.env,
                            }
                        },
                    )
                case SSHLog.Full:
                    self.__logger.info(
                        self.__msg_completed_async(result.rc),
                        extra={
                            "data": {
                                "Host": self.__client.host,
                                "User": self.__client.user,
                                "Command": self.command,
                                "Input": self.input,
                                "Working directory": self.cwd,
                                "Extra environment": self.env,
                                "Output": result.stdout,
                                "Error output": result.stderr,
                            }
                        },
                    )
                case _:
                    pass

        if raise_on_error and result.rc != 0:
            result.throw()

        return result

    def send_eof(self) -> None:
        """
        Send EOF to standard input to indicate that there will be no more
        input data.

        :raises RuntimeError: If the process is not running.
        """
        if self.__channel is None:
            raise RuntimeError("Calling send_eof on process that is not running.")

        self.__channel.send_eof()

    def send_signal(self, sig: str) -> None:
        """
        Send signal to the running process.

        :raises RuntimeError: If the process is not running.
        """
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

    def _build_complete_command(self, command: str, *, cwd: str | None, env: dict[str, Any]) -> str:
        out = ""

        # Set environment variables
        for key, value in env.items():
            out += f"export {key}={shlex.quote(str(value))}\n"

        # Set working directory
        if cwd is not None:
            out += f"cd {shlex.quote(cwd)}\n"

        if out:
            out += "\n"

        out += command

        return out

    def _escape_command(self, command: str) -> str:
        """
        We call the command as $shell '$command', e.g. bash -c '$command'

        We need to escape ' inside the command to make it work correctly.
        """
        return command.replace("'", "'\"'\"'")

    def _get_log_level(self, input_log_level: SSHLog) -> SSHLog:
        debug = os.getenv("MH_SSH_DEBUG", "no")
        if debug.lower() in ["true", "yes", "1"]:
            return SSHLog.Full

        return input_log_level

    def __msg_id(self) -> str:
        return self.__logger.colorize(f"#{self.id}", c.Style.BRIGHT, c.Fore.BLUE)

    def __msg_rc(self, rc: int) -> str:
        if rc == 0:
            return self.__logger.colorize(rc, c.Style.BRIGHT, c.Fore.GREEN)

        return self.__logger.colorize(rc, c.Style.BRIGHT, c.Fore.RED)

    def __msg_execution(self) -> str:
        return f'{self.__logger.colorize("Executing command", c.Style.BRIGHT)} ' + self.__msg_id()

    def __msg_completed_sync(self, rc: int) -> str:
        return "Previous command completed with exit code " + self.__msg_rc(rc)

    def __msg_completed_async(self, rc: int) -> str:
        return (
            self.__logger.colorize("Command ", c.Style.BRIGHT)
            + self.__msg_id()
            + self.__logger.colorize(" completed with exit code ", c.Style.BRIGHT)
            + self.__msg_rc(rc)
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.wait()


class SSHBashProcess(SSHProcess):
    """
    SSH Process with Bash.

    .. note::

        You should not create instances of this class yourself. Use method
        :meth:`SSHClient.run`, :meth:`SSHClient.exec`,
        :meth:`SSHClient.async_run` and :meth:`SSHClient.async_exec` from
        :class:`SSHClient` to execute a command over SSH.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, shell="/usr/bin/bash -c")


class SSHPowerShellProcess(SSHProcess):
    """
    SSH Process with Powershell.

    .. note::

        You should not create instances of this class yourself. Use method
        :meth:`SSHClient.run`, :meth:`SSHClient.exec`,
        :meth:`SSHClient.async_run` and :meth:`SSHClient.async_exec` from
        :class:`SSHClient` to execute a command over SSH.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, shell="powershell -NonInteractive -Command")

    def _build_complete_command(self, command: str, *, cwd: str | None, env: dict[str, Any]) -> str:
        out = ""

        # Set environment variables
        for key, value in env.items():
            out += f"$Env:{key} = {shlex.quote(str(value))}\n"

        # Set working directory
        if cwd is not None:
            out += f"cd {shlex.quote(cwd)}\n"

        if out:
            out += "\n"

        out += command

        return out

    def _escape_command(self, command: str) -> str:
        """
        We call the command as $shell '$command', e.g. bash -c '$command'

        We need to escape ' inside the command to make it work correctly.
        """
        return command.replace("'", "''").replace('"', '\\"')


class SSHProcessResult(object):
    """
    SSH Process result.
    """

    def __init__(self, rc: int, stdout: list[str], stderr: list[str]) -> None:
        """
        :param rc: Return code.
        :type rc: int
        :param stdout: Standard output, line by line.
        :type stdout: list[str]
        :param stderr: Standard error output, line by line.
        :type stderr: list[str]
        """
        self.rc = rc
        self.stdout: str = "\n".join(stdout)
        self.stderr: str = "\n".join(stderr)
        self.stdout_lines: list[str] = stdout
        self.stderr_lines: list[str] = stderr

        self._error: SSHProcessError | None = None

    def throw(self) -> NoReturn:
        """
        Raise SSHProcessError for this command manually.

        The error is available to raise even if return code is 0. Therefore the
        caller may choose to raise the error on any condition, not just the
        return code.

        :raises SSHProcessError: Error generated for this process result.
        """
        if self._error is None:
            raise ValueError("No error is set.")

        raise self._error


class SSHProcessError(Exception):
    """
    SSH Process Error.
    """

    def __init__(
        self,
        id: int,
        command: str,
        rc: int,
        cwd: str | None,
        env: dict[str, Any],
        input: str | None,
        stdout: str,
        stderr: str,
    ) -> None:
        pretty_env = ""
        for key, value in env.items():
            pretty_env += f"{key}={value}\n"

        def dumps(value) -> str:
            if not value:
                return ""

            return "\n" + textwrap.indent(value, " " * 12)

        super().__init__(
            textwrap.dedent(
                f"""
        Command #{id} exited with return code {rc}:
          Command:{dumps(command)}
          CWD:{dumps(cwd)}
          Env:{dumps(pretty_env.strip())}
          Output:{dumps(stdout)}
          Error output:{dumps(stderr)}
        """
            )
        )

        self.id: int = id
        self.command: tuple[str] = (command,)
        self.rc: int = rc
        self.cwd: str | None = cwd
        self.env: dict[str, Any] = env
        self.input: str | None = input
        self.stdout: str = stdout
        self.stderr: str = stderr


class SSHAuthenticationError(Exception):
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        message: str,
    ) -> None:
        super().__init__(f'Unable to authenticate as "{user}" at {host}:{port} over SSH: {message}')


class SSHClient(object):
    """
    Interactive SSH client.

    .. code-block:: python
        :caption: Example: Blocking call

        # Connect to SSH server, it is automatically disconnected when leaving the with statement
        with SSHClient(host, user=username, password=password, logger=logger) as ssh:
            result = ssh.run('echo Hello World')
            print(result.rc)
            print(result.stdout)

            result = ssh.run('cat', input='Hello World')
            print(result.rc)
            print(result.stdout)

    .. code-block:: python
        :caption: Example: Non-blocking call

        # Connect to SSH server, it is automatically disconnected when leaving the with statement
        with SSHClient(host, user=username, password=password, logger=logger) as ssh:
            # The process is executed, but it does not block. In order to wait for it to finish, run process.wait()
            process = ssh.async_run('echo Hello World')
            result = process.wait()
            print(result.rc)
            print(result.stdout)

            # You can write to stdin directly in asynchronous run
            process = ssh.async_run('cat')
            process.stdin.write('Hello World')
            process.send_eof()
            result = process.wait()
            print(result.rc)
            print(result.stdout)

            # You can also work with inputs and outputs more interactively.
            # The process is automatically waited when leaving the with statement.
            with ssh.async_run('bash') as process:
                process.stdin.write('echo Hello World\\n')
                print(next(process.stdout))

                process.stdin.write('echo This works as well\\n')
                print(next(process.stdout))

    .. note::

        It is possible to set ``MH_SSH_DEBUG=yes`` environment variable to
        log output and exit status to from commands, regardless of what log
        level is used. This essentially enforces the :attr:`SSHLog.Full` level.
    """

    def __init__(
        self,
        host: str,
        *,
        user: str,
        password: str,
        port: int = 22,
        shell: Type[SSHProcess] = SSHBashProcess,
        logger: MultihostLogger,
    ) -> None:
        """
        :param host: Host name to connect to.
        :type host: BaseRole | str
        :param user: Username to authenticate.
        :type user: str
        :param password: Password.
        :type password: str
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param port: SSH port, defaults to 22
        :type port: int, optional
        :param shell: User shell used to run commands, defaults to SSHBashProcess
        :type shell: str, optional
        """
        self.host: str = host
        self.user: str = user
        self.password: str = password
        self.port: int = port
        self.shell: Type[SSHProcess] = shell
        self.logger: MultihostLogger = logger

        self.__conn: LibsshSession = LibsshSession()

    @property
    def connected(self) -> bool:
        """
        :return: True if the client is connected, False otherwise.
        :rtype: bool
        """
        return self.__conn.is_connected

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
        )

        try:
            self.__conn.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                port=self.port,
                host_key_checking=False,
            )
        except LibsshSessionException as e:
            raise SSHAuthenticationError(self.host, self.port, self.user, e.message)

    def disconnect(self) -> None:
        """
        Disconnect client.
        """
        self.logger.info(
            self.logger.colorize("Closing SSH connection to ", c.Style.BRIGHT)
            + self.logger.colorize(self.host, c.Fore.BLUE, c.Style.BRIGHT)
        )

        self.__conn.disconnect()

    def async_run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | None = None,
        read_timeout: float = 30,
        log_level: SSHLog = SSHLog.Full,
    ) -> SSHProcess:
        """
        Non-blocking command call.

        The command is run under shell specified in the constructor and it is
        executed immediately, however it does not wait for the command to finish.

        :param command: Command to run.
        :type command: str
        :param cwd: Working directory, defaults to None (= do not change)
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | None, optional
        :param read_timeout: Timeout in seconds, how long should the client wait for output, defaults to 30 seconds
        :type read_timeout: float, optional
        :param log_level: Log level, defaults to SSHLog.Full
        :type log_level: SSHLog, optional
        :return: Instance of :class:`SSHProcess`, the process is already running.
        :rtype: SSHProcess
        """
        if not isinstance(command, str):
            raise ValueError("Parameter command is not a string, did you mean async_exec() instead of async_run()?")

        self.connect()

        process = self.shell(
            command=command,
            cwd=cwd,
            env=env,
            input=input,
            client=self,
            conn=self.__conn,
            read_timeout=read_timeout,
            logger=self.logger,
            log_level=log_level,
            sync_exec=False,
        )

        process.run()
        return process

    def run(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | None = None,
        read_timeout: float = 2,
        log_level: SSHLog = SSHLog.Full,
        raise_on_error: bool = True,
    ) -> SSHProcessResult:
        """
        Blocking command call.

        The command is run under shell specified in the constructor and it is
        executed immediately. It waits for the command to finish and returns
        its result.

        :param command: Command to run.
        :type command: str
        :param cwd: Working directory, defaults to None (= do not change)
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | None, optional
        :param read_timeout: Timeout in seconds, how long should the client wait
            for output, defaults to 30 seconds
        :type read_timeout: float, optional
        :param log_level: Log level, defaults to SSHLog.Full
        :type log_level: SSHLog, optional
        :param raise_on_error: If True, raise :class:`SSHProcessError` if
            command exited with non-zero return code, defaults to True
        :type raise_on_error: bool, optional
        :raises SSHProcessError: If ``raise_on_error`` is True and the command exited with non-zero return code.
        :return: Command result.
        :rtype: SSHProcessResult
        """
        if not isinstance(command, str):
            raise ValueError("Parameter command is not a string, did you mean exec() instead of run()?")

        self.connect()

        process = self.shell(
            command=command,
            cwd=cwd,
            env=env,
            input=input,
            client=self,
            conn=self.__conn,
            read_timeout=read_timeout,
            logger=self.logger,
            log_level=log_level,
            sync_exec=True,
        )

        process.run()

        return process.wait(raise_on_error=raise_on_error)

    def async_exec(
        self,
        argv: list[Any],
        *,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | None = None,
        read_timeout: float = 2,
        log_level: SSHLog = SSHLog.Full,
    ) -> SSHProcess:
        """
        Non-blocking command call.

        The command is run under shell specified in the constructor and it is
        executed immediately, however it does not wait for the command to finish.

        The command is provided as ``argv`` list.

        :param argv: Command to run.
        :type argv: list[Any]
        :param cwd: Working directory, defaults to None (= do not change)
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | None, optional
        :param read_timeout: Timeout in seconds, how long should the client wait for output, defaults to 30 seconds
        :type read_timeout: float, optional
        :param log_level: Log level, defaults to SSHLog.Full
        :type log_level: SSHLog, optional
        :return: Instance of :class:`SSHProcess`, the process is already running.
        :rtype: SSHProcess
        """
        if not isinstance(argv, list):
            raise ValueError("Parameter argv is not a list, did you mean async_run() instead of async_exec()?")

        argv = [str(x) for x in argv]
        command = shlex.join(argv)

        return self.async_run(
            command,
            cwd=cwd,
            env=env,
            input=input,
            read_timeout=read_timeout,
            log_level=log_level,
        )

    def exec(
        self,
        argv: list[Any],
        *,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | None = None,
        read_timeout: float = 2,
        log_level: SSHLog = SSHLog.Full,
        raise_on_error: bool = True,
    ) -> SSHProcessResult:
        """
        Blocking command call.

        The command is run under shell specified in the constructor and it is
        executed immediately. It waits for the command to finish and returns its
        result.

        The command is provided as ``argv`` list.

        :param argv: Command to run.
        :type argv: list[Any]
        :param cwd: Working directory, defaults to None (= do not change)
        :type cwd: str | None, optional
        :param env: Additional environment variables, defaults to None
        :type env: dict[str, Any] | None, optional
        :param input: Content of standard input, defaults to None
        :type input: str | None, optional
        :param read_timeout: Timeout in seconds, how long should the client wait
            for output, defaults to 30 seconds
        :type read_timeout: float, optional
        :param log_level: Log level, defaults to SSHLog.Full
        :type log_level: SSHLog, optional
        :param raise_on_error: If True, raise :class:`SSHProcessError` if
            command exited with non-zero return code, defaults to True
        :type raise_on_error: bool, optional
        :raises SSHProcessError: If ``raise_on_error`` is True and the command exited with non-zero return code.
        :return: Command result.
        :rtype: SSHProcessResult
        """
        if not isinstance(argv, list):
            raise ValueError("Parameter argv is not a list, did you mean run() instead of exec()?")

        argv = [str(x) for x in argv]
        command = shlex.join(argv)

        return self.run(
            command,
            cwd=cwd,
            env=env,
            input=input,
            read_timeout=read_timeout,
            log_level=log_level,
            raise_on_error=raise_on_error,
        )

    def expect(
        self,
        expect_script: str,
        *,
        verbose: bool = True,
        raise_on_error: bool = False,
    ) -> SSHProcessResult:
        """
        Run expect script.

        :param expect_script: Expect script.
        :type expect_script: str
        :param verbose: Enable expect debug output (-d), default to True.
        :type verbose: bool, optional
        :param raise_on_error: If True, raise :class:`SSHProcessError` if
            command exited with non-zero return code, defaults to False
        :type raise_on_error: bool, optional
        :return: Expect script result.
        :rtype: SSHProcessResult
        """
        args = ["-d"] if verbose else []
        return self.exec(["/bin/expect", *args], input=expect_script, raise_on_error=raise_on_error)

    def expect_nobody(
        self,
        expect_script: str,
        *,
        verbose: bool = True,
        raise_on_error: bool = False,
    ) -> SSHProcessResult:
        """
        Run expect script as user nobody.

        The main use case is to avoid running the command as root if the client
        is connected to the root user SSH session.

        :param expect_script: Expect script.
        :type expect_script: str
        :param verbose: Enable expect debug output (-d), default to True.
        :type verbose: bool, optional
        :param raise_on_error: If True, raise :class:`SSHProcessError` if
            command exited with non-zero return code, defaults to False
        :type raise_on_error: bool, optional
        :return: Expect return code.
        :rtype: SSHProcessResult
        """
        args = " -d" if verbose else ""
        return self.run(
            f'su --shell /bin/sh nobody -c "/bin/expect{args}"', input=expect_script, raise_on_error=raise_on_error
        )

    def __enter__(self) -> SSHClient:
        """
        Connect to the host.

        :return: SSHClient instance.
        :rtype: SSHClient
        """
        self.connect()
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        """
        Disconnect.
        """
        self.disconnect()
