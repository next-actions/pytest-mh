from __future__ import annotations

from enum import Enum, auto
from typing import Any, Type, TypeAlias

from .ssh import SSHClient, SSHPowerShellProcess, SSHProcess


class CLIBuilder(object):
    class option(Enum):
        """
        Command line parameter types.
        """

        PLAIN = auto()
        """
        Use plain parameter value without any modification.
        """

        VALUE = auto()
        """
        Use parameter value but enclose it in quotes in script mode.
        """

        SWITCH = auto()
        """
        Parameter is a switch which is enabled if value is True.
        """

        POSITIONAL = auto()
        """
        Parameter is a positional argument.
        """

    def __init__(self, ssh: SSHClient) -> None:
        self.__shell: Type[SSHProcess] = ssh.shell
        self.__prefix: str = "-" if self.__match_shell(SSHPowerShellProcess) else "--"

    def command(self, command: str, args: CLIBuilderArgs) -> str:
        return " ".join(self.__build(command, args, quote_value=True))

    def argv(self, command: str, args: CLIBuilderArgs) -> list[str]:
        return self.__build(command, args, quote_value=False)

    def args(self, args: CLIBuilderArgs, quote_value=False) -> list[str]:
        return self.__build(None, args, quote_value)

    def __match_shell(self, shell: Type[SSHProcess]):
        return issubclass(self.__shell, shell)

    def __build(self, command: str | None, args: CLIBuilderArgs, quote_value: bool) -> list[str]:
        def _get_option(name: str) -> str:
            return self.__prefix + name

        def _get_value(value: Any) -> str:
            return str(value) if not quote_value else f"'{value}'"

        argv = [command] if command is not None else []
        for key, item in args.items():
            if item is None:
                continue

            (type, value) = item
            if value is None:
                continue

            match type:
                case self.option.POSITIONAL:
                    argv.append(_get_value(value))
                case self.option.SWITCH:
                    if self.__match_shell(SSHPowerShellProcess):
                        argv.append(f'{_get_option(key)}:{"$True" if value else "$False"}')
                    else:
                        if value:
                            argv.append(_get_option(key))
                case self.option.VALUE:
                    argv.append(_get_option(key))
                    argv.append(_get_value(value))
                case self.option.PLAIN:
                    argv.append(_get_option(key))
                    argv.append(str(value))
                case _:
                    raise ValueError(f"Unknown option type: {type}")

        return argv


CLIBuilderArgs: TypeAlias = dict[str, tuple[CLIBuilder.option, Any] | None]
"""CLIBuilder args format."""
