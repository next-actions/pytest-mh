from __future__ import annotations

import signal
import subprocess
import threading
from typing import IO, TYPE_CHECKING, Any, Generator, Self

import colorama as c

from pytest_mh.conn import Process, ProcessLogLevel

from .._private.logging import MultihostLogger
from . import Connection, ConnectionError, ProcessError, ProcessInputBuffer, ProcessResult, ProcessTimeoutError, Shell

if TYPE_CHECKING:
    from .. import MultihostHost

__all__ = [
    "ContainerClient",
    "ContainerConnectionError",
    "ContainerProcess",
    "ContainerProcessError",
    "ContainerProcessTimeoutError",
    "ContainerInputBuffer",
    "ContainerProcessResult",
]


class ContainerInputBuffer(ProcessInputBuffer):
    """
    Container Input Buffer.

    Allows to write into stdin of opened Container channel.
    """

    def __init__(self, pipe: IO[bytes]) -> None:
        """
        :param pipe: Input pipe.
        :type pipe: BufferedWriter
        """
        self.pipe: IO[bytes] = pipe

    def write(self, data: str | bytes) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")

        self.pipe.write(data)

    def flush(self) -> None:
        """
        Flush the input stream.
        """
        self.pipe.flush()

    def close(self) -> None:
        """
        Close the input stream.
        """
        self.pipe.close()


class ContainerOutputBuffer(Generator):
    """
    Container Output Buffer.

    Reads from stdout or stderr from the running process and makes each line
    of the data accessible through a generator.
    """

    def __init__(self, pipe: IO[bytes]):
        """
        :param pipe: Input pipe.
        :type pipe: BufferedWriter
        """
        self.pipe: IO[bytes] = pipe

        self.eof: bool = False
        self.lines: list[str] = []

        # If a buffer is full the process is paused waiting for the buffer to be
        # read. This can cause deadlock under certain situations, therefore we
        # need to keep reading the buffer continuously in another thread.
        self._index: int = 0
        self._lock: threading.Condition = threading.Condition()
        self._thread = threading.Thread(target=self._read)
        self._thread.daemon = True
        self._thread.start()

    def _read(self) -> None:
        while not self.eof:
            with self._lock:
                line: bytes = self.pipe.readline()
                if line:
                    self.lines.append(line.decode("utf-8").rstrip("\n"))
                else:
                    self.eof = True

                self._lock.notify()

    def finish(self) -> None:
        """
        Read all remaining data.
        """
        self._thread.join()

    def send(self, value: Any):
        with self._lock:
            self._lock.wait_for(lambda: self.eof or self._index < len(self.lines))
            if self.eof and self._index >= len(self.lines):
                raise StopIteration

            line: str = self.lines[self._index]
            self._index += 1
            return line

    def throw(self, typ, val=None, tb=None):
        super().throw(typ, val, tb)


class ContainerProcessError(ProcessError):
    """
    Container Process Error.
    """

    pass


class ContainerProcessTimeoutError(ProcessTimeoutError):
    """
    Container Process Timeout Error.
    """

    pass


class ContainerProcessResult(ProcessResult[ContainerProcessError]):
    """
    Container Process result.
    """

    pass


class ContainerProcess(Process[ContainerProcessResult, ContainerInputBuffer, ContainerProcessTimeoutError]):
    """
    Container Process manager.
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
        client: ContainerClient,
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
        :param client: Container client.
        :type client: ContainerClient
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
                "Engine": client.engine,
                "Container": client.container_name,
                "User": client.user,
            },
        )

        self.__client: ContainerClient = client

        self.__stdout: ContainerOutputBuffer | None = None
        self.__stderr: ContainerOutputBuffer | None = None
        self.__stdin: ContainerInputBuffer | None = None
        self.__popen: subprocess.Popen | None = None

    @property
    def in_progress(self) -> bool:
        return self.__popen is not None

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
    def stdin(self) -> ContainerInputBuffer:
        if not self.in_progress or self.__stdin is None:
            raise RuntimeError("Accessing stdin on a process that is not running.")

        return self.__stdin

    def _run(self) -> None:
        """
        Execute the command.

        This is an internal method called by :meth:`run` after executing
        generic code.
        """
        command = "{sudo} {engine} exec --interactive {name} {command}".format(
            sudo="sudo -k -S --prompt=''" if self.__client.sudo else "",
            engine=self.__client.engine,
            name=self.__client.container_name,
            command=self.full_command_line,
        ).lstrip()

        try:
            self.__popen = subprocess.Popen(
                args=command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )

            # This is to satisfy mypy
            if self.__popen.stdout is None or self.__popen.stderr is None or self.__popen.stdin is None:
                raise RuntimeError("subprocess.Popen did not correctly open pipes")

            self.__stdin = ContainerInputBuffer(self.__popen.stdin)
            self.__stdout = ContainerOutputBuffer(self.__popen.stdout)
            self.__stderr = ContainerOutputBuffer(self.__popen.stderr)

            if self.__client.sudo and self.__client.sudo_password is not None:
                self.stdin.write(f"{self.__client.sudo_password}\n")
                self.stdin.flush()

            if self.input is not None:
                self.stdin.write(self.input)
                self.stdin.flush()

        except Exception:
            self._close()
            raise

    def _wait(self) -> ContainerProcessResult:
        """
        Wait for the command to finish.

        EOF is send to standard input to indicate that there will be no
        additional input data. Then it waits for the command to finish.

        This is an internal method called by :meth:`run` after executing
        generic code.

        :return: Command result.
        :rtype: ContainerProcessResult
        """
        if self.__popen is None or self.__stdout is None or self.__stderr is None:
            raise RuntimeError("Calling wait on process that has not yet started.")

        try:
            # Notify the program that there will be no more input
            self.send_eof()

            # Read remaining output, this will finish the output generator and append
            # remaining lines to self.__stdout and self.__stderr buffers.
            self.__stdout.finish()
            self.__stderr.finish()

            # Wait for the program to finish and get the exit code.
            code = self.__popen.wait()

            error = ContainerProcessError(
                code, self.id, self.command, self.cwd, self.env, self.input, self.__stdout.lines, self.__stderr.lines
            )

            result = ContainerProcessResult(code, self.__stdout.lines, self.__stderr.lines, error)
        except TimeoutError as e:
            raise ContainerProcessTimeoutError(
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
        if self.__popen is None or self.__stdin is None:
            raise RuntimeError("Calling send_eof on process that is not running.")

        self.__stdin.close()

    def send_signal(self, sig: signal.Signals) -> None:
        if self.__popen is None:
            raise RuntimeError("Calling send_signal on process that is not running.")

        self.__popen.send_signal(sig)

    def _close(self) -> None:
        if self.__popen is None:
            return

        if self.__popen.returncode is None:
            self.__popen.kill()

        self.__popen = None
        self.__stdout = None
        self.__stderr = None
        self.__stdin = None


class ContainerConnectionError(ConnectionError):
    """
    Unable to connect to the container.
    """

    def __init__(
        self,
        engine: str,
        container_name: str,
        *,
        user: str,
        sudo: bool,
    ) -> None:
        super().__init__(f"Unable to connect to {engine} container {container_name}, user={user}, sudo={sudo}")


class ContainerClient(Connection[ContainerProcess, ContainerProcessResult]):
    """
    Interactive podman and docker client.
    """

    def __init__(
        self,
        engine: str,
        container_name: str,
        *,
        user: str,
        sudo: bool = False,
        sudo_password: str | None = None,
        shell: Shell,
        logger: MultihostLogger,
        timeout: int = 300,
    ) -> None:
        """
        :param container_name: Container name.
        :type container_name: str
        :param user: Username that will be used to execute commands.
        :type user: str
        :param sudo: Run podman under root, defaults to ``False``.
        :type sudo: bool
        :param sudo_password: SUDO password, defaults to ``None``.
        :type sudo_password: str | None
        :param shell: User shell used to run commands, defaults to ContainerBashProcess
        :type shell: str, optional
        :param logger: Multihost logger.
        :type logger: MultihostLogger
        :param timeout: Timeout in seconds (defaults to 300), value
            ``0`` means that timeout is disabled.
        :type timeout: int
        """
        super().__init__(shell=shell, logger=logger, timeout=timeout)

        if engine not in ("podman", "docker"):
            raise ValueError(f"Unsupported container engine {engine}, expected podman or docker!")

        self.engine: str = engine
        self.container_name: str = container_name
        self.user: str = user

        self.sudo: bool = sudo
        self.sudo_password: str | None = sudo_password

        self._connected: bool = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """
        Connect to the host.

        :raises ContainerAuthenticationError: If user fails to authenticate.
        """
        if self.connected:
            return

        self.logger.info(
            self.logger.colorize("Checking container ", c.Style.BRIGHT)
            + self.logger.colorize(self.container_name, c.Fore.BLUE, c.Style.BRIGHT)
            + self.logger.colorize(f" using {self.engine}", c.Style.BRIGHT)
        )

        # We need to mark it as connected here to avoid recursion from `run`
        self._connected = True

        # Check that the container is reachable
        result = self.run("exit 0", raise_on_error=False, log_level=ProcessLogLevel.Error)
        if result.rc != 0:
            self._connected = False
            raise ContainerConnectionError(self.engine, self.container_name, user=self.user, sudo=self.sudo)

    def disconnect(self) -> None:
        self._connected = False

    def create_process(
        self,
        *,
        command: str,
        cwd: str | None = None,
        env: dict[str, Any] | None = None,
        input: str | bytes | None = None,
        log_level: ProcessLogLevel,
        blocking_call: bool,
    ) -> ContainerProcess:
        return ContainerProcess(
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
        )

    @classmethod
    def from_confdict(cls, host: MultihostHost, confdict: dict[str, Any]) -> Self:
        engine: str = confdict["type"]
        container: str | None = confdict.get("container", None)
        user: str = confdict.get("user", "root")
        sudo: bool = confdict.get("sudo", False)
        sudo_password: str | None = confdict.get("sudo_password", None)
        timeout: int = confdict.get("timeout", 300)

        if container is None:
            raise ValueError("Container name is not set!")

        return cls(
            engine=engine,
            container_name=container,
            user=user,
            sudo=sudo,
            sudo_password=sudo_password,
            logger=host.logger,
            shell=host.shell,
            timeout=timeout,
        )
