from __future__ import annotations

from enum import Enum, auto
from typing import Any, Callable, Type, TypeAlias

from .conn import Powershell, Shell

__all__ = [
    "CLIBuilder",
]


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

    def __init__(self, shell: Shell) -> None:
        """
        :param shell: Target shell.
        :type shell: Shell
        """
        self.__shell: Shell = shell
        self.__prefix: str = "-" if self.__match_shell(Powershell) else "--"

    def command(self, command: str, args: CLIBuilderArgs) -> str:
        """
        Build full command line and return it as a string.

        Output can be passed directly to :meth:`Connection.run
        <pytest_mh.conn.Connection.run>` (``host.conn.run``).

        .. code-block:: python
            :caption: Example

            cli = CLIBuilder(Bash())
            args: CLIBuilderArgs = {
                "password": (cli.option.VALUE, None),     # None values are ignored
                "home": (cli.option.VALUE, "/home/jdoe"), # --home '/home/jdoe'
                "enabled": (cli.option.SWITCH, True),     # --enabled
                "login": (cli.option.POSITIONAL, "jdoe"), # 'jdoe'
            }

            line = cli.command("add-user", args)
            # add-user --home '/home/jdoe' --enabled 'jdoe'

        :param command: Command to call
        :type command: str
        :param args: Command's arguments
        :type args: CLIBuilderArgs
        :return: Full command line as string.
        :rtype: str
        """
        return " ".join(self.__build(command, args, quote_value=True))

    def argv(self, command: str, args: CLIBuilderArgs) -> list[str]:
        """
        Build full command line and return it it as list of arguments (full
        argv).

        Output can be passed directly to :meth:`Connection.exec
        <pytest_mh.conn.Connection.exec>` (``host.conn.exec``).

        .. code-block:: python
            :caption: Example

            cli = CLIBuilder(Bash())
            args: CLIBuilderArgs = {
                "password": (cli.option.VALUE, None),     # None values are ignored
                "home": (cli.option.VALUE, "/home/jdoe"), # --home '/home/jdoe'
                "enabled": (cli.option.SWITCH, True),     # --enabled
                "login": (cli.option.POSITIONAL, "jdoe"), # 'jdoe'
            }

            line = cli.argv("add-user", args)
            # ["add-user", "--home", "/home/jdoe", "--enabled", "jdoe"]

        :param command: Command to call
        :type command: str
        :param args: Command's arguments
        :type args: CLIBuilderArgs
        :return: Full command line as argv
        :rtype: list[str]
        """
        return self.__build(command, args, quote_value=False)

    def args(self, args: CLIBuilderArgs, *, quote_value=False) -> list[str]:
        """
        Build command's arguments and return them as a list (argv without
        command).

        Output can be used for additional processing by the caller.

        .. code-block:: python
            :caption: Example

            cli = CLIBuilder(Bash())
            args: CLIBuilderArgs = {
                "password": (cli.option.VALUE, None),     # None values are ignored
                "home": (cli.option.VALUE, "/home/jdoe"), # --home '/home/jdoe'
                "enabled": (cli.option.SWITCH, True),     # --enabled
                "login": (cli.option.POSITIONAL, "jdoe"), # 'jdoe'
            }

            line = cli.args(args)
            # ["--home", "/home/jdoe", "--enabled", "jdoe"]

            host.conn.run(f"user-add --encrypt-home {' '.join(line)}")

        :param args: Command's argument
        :type args: CLIBuilderArgs
        :param quote_value: True if values should enclosed with quotes, defaults to False
        :type quote_value: bool, optional
        :return: Arguments ready to use in command line (argv without command)
        :rtype: list[str]
        """
        return self.__build(None, args, quote_value)

    def __match_shell(self, shell: Type[Shell]):
        return isinstance(self.__shell, shell)

    def __build(self, command: str | None, args: CLIBuilderArgs, quote_value: bool) -> list[str]:
        def _get_option(name: str) -> str:
            return self.__prefix + name

        def _get_value(value: Any) -> str:
            return str(value) if not quote_value else f"'{value}'"

        def _add_argv(argv: list[str], key: str | None, value: Any, getvaluefn: Callable[[Any], str]) -> None:
            value = value if isinstance(value, list) else [value]
            for v in value:
                if key is not None:
                    argv.append(_get_option(key))

                argv.append(getvaluefn(v))

        argv = [command] if command is not None else []
        for key, item in args.items():
            if item is None:
                continue

            (type, value) = item
            if value is None:
                continue

            match type:
                case self.option.POSITIONAL:
                    _add_argv(argv, None, value, _get_value)
                case self.option.SWITCH:
                    if self.__match_shell(Powershell):
                        argv.append(f'{_get_option(key)}:{"$True" if value else "$False"}')
                    else:
                        if value:
                            argv.append(_get_option(key))
                case self.option.VALUE:
                    _add_argv(argv, key, value, _get_value)
                case self.option.PLAIN:
                    _add_argv(argv, key, value, str)
                case _:
                    raise ValueError(f"Unknown option type: {type}")

        return argv


CLIBuilderArgs: TypeAlias = dict[str, tuple[CLIBuilder.option, Any] | None]
"""CLIBuilder args format."""
