"""Testing authentications and authorization mechanisms."""

from __future__ import annotations

from pytest_mh import MultihostHost, MultihostUtility

__all__ = [
    "SUDOUtils",
]


class SUDOUtils(MultihostUtility[MultihostHost]):
    """
    Methods for testing authentication and authorization via sudo.
    """

    def run(self, username: str, password: str | None = None, *, command: str) -> bool:
        """
        Execute sudo command.

        :param username: Username that calls sudo.
        :type username: str
        :param password: User password, defaults to None
        :type password: str | None, optional
        :param command: Command to execute (make sure to properly escape any quotes).
        :type command: str
        :return: True if the command was successful, False if the command failed or the user can not run sudo.
        :rtype: bool
        """
        result = self.conn.run(f'su - "{username}" -c "sudo --stdin {command}"', input=password, raise_on_error=False)

        return result.rc == 0

    def list(self, username: str, password: str | None = None, *, expected: list[str] | None = None) -> bool:
        """
        List commands that the user can run under sudo.

        :param username: Username that runs sudo.
        :type username: str
        :param password: User password, defaults to None
        :type password: str | None, optional
        :param expected: List of expected commands (formatted as sudo output), defaults to None
        :type expected: list[str] | None, optional
        :return: True if the user can run sudo and allowed commands match expected commands (if set), False otherwise.
        :rtype: bool
        """
        result = self.conn.run(f'su - "{username}" -c "sudo --stdin -l"', input=password, raise_on_error=False)
        if result.rc != 0:
            return False

        if expected is None:
            return True

        allowed = []
        for line in reversed(result.stdout_lines):
            if not line.startswith("    "):
                break
            allowed.append(line.strip())

        for line in expected:
            if line not in allowed:
                return False
            allowed.remove(line)

        if len(allowed) > 0:
            return False

        return True
