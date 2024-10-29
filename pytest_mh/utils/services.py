from __future__ import annotations

from collections import deque
from typing import Self

from .. import MultihostHost, MultihostReentrantUtility
from ..conn import Process, ProcessLogLevel, ProcessResult

__all__ = ["SystemdServices"]


class SystemdServices(MultihostReentrantUtility[MultihostHost]):
    """
    Manage remote services.
    """

    def __init__(self, host: MultihostHost) -> None:
        super().__init__(host)
        self.initial_states: dict[str, bool] = {}
        self.__states: deque[dict[str, bool]] = deque()

    def __enter__(self) -> Self:
        """
        Saves current state.

        :return: Self.
        :rtype: Self
        """
        self.__states.append(self.initial_states)
        self.initial_states = {}

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Revert all changes done during current context.
        """
        # Restart all services that were touched
        self.reload_daemon()
        for service, state in self.initial_states.items():
            self.logger.info(f'systemd: restoring "{service}" to {"started" if state else "stopped"}')
            self.host.conn.run(
                self._debug_failure(service, f'systemctl stop "{service}"'),
                raise_on_error=False,
                log_level=ProcessLogLevel.Error,
            )
            if state:
                self.host.conn.run(
                    self._debug_failure(service, f'systemctl start "{service}"'),
                    raise_on_error=False,
                    log_level=ProcessLogLevel.Error,
                )

        self.initial_states = self.__states.pop()

    def async_start(self, service: str) -> Process:
        """
        Start a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be started. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: Process
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: starting "{service}" asynchronously')
        return self.host.conn.async_run(
            self._debug_failure(service, f'systemctl reset-failed "{service}"; systemctl start "{service}"'),
            log_level=ProcessLogLevel.Error,
        )

    def start(self, service: str, raise_on_error: bool = True) -> ProcessResult:
        """
        Start a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be started. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: starting "{service}"')
        return self.host.conn.run(
            self._debug_failure(service, f'systemctl reset-failed "{service}"; systemctl start "{service}"'),
            raise_on_error=raise_on_error,
            log_level=ProcessLogLevel.Error,
        )

    def async_stop(self, service: str) -> Process:
        """
        Stop a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be stopped. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: Process
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: stopping "{service}" asynchronously')
        return self.host.conn.async_run(
            self._debug_failure(service, f'systemctl stop "{service}"'), log_level=ProcessLogLevel.Error
        )

    def stop(self, service: str, raise_on_error: bool = True) -> ProcessResult:
        """
        Stop a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be stoped. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: stopping "{service}"')
        return self.host.conn.run(
            self._debug_failure(service, f'systemctl stop "{service}"'),
            raise_on_error=raise_on_error,
            log_level=ProcessLogLevel.Error,
        )

    def async_restart(self, service: str) -> Process:
        """
        Restart a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be restarted. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: Process
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: restarting "{service}" asynchronously')
        return self.host.conn.async_run(
            self._debug_failure(service, f'systemctl reset-failed "{service}"; systemctl restart "{service}"'),
            log_level=ProcessLogLevel.Error,
        )

    def restart(self, service: str, raise_on_error: bool = True) -> ProcessResult:
        """
        Restart a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be restarted. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: restarting "{service}"')
        return self.host.conn.run(
            self._debug_failure(service, f'systemctl reset-failed "{service}"; systemctl restart "{service}"'),
            raise_on_error=raise_on_error,
            log_level=ProcessLogLevel.Error,
        )

    def async_reload(self, service: str) -> Process:
        """
        Reload a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be reloaded. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: Process
        """
        self.logger.info(f'systemd: reloading "{service}" asynchronously')
        return self.host.conn.async_run(
            self._debug_failure(service, f'systemctl reload "{service}"'), log_level=ProcessLogLevel.Error
        )

    def reload(self, service: str, raise_on_error: bool = True) -> ProcessResult:
        """
        Reload a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be reloaded. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        self.logger.info(f'systemd: reloading "{service}"')
        return self.host.conn.run(
            self._debug_failure(service, f'systemctl reload "{service}"'),
            raise_on_error=raise_on_error,
            log_level=ProcessLogLevel.Error,
        )

    def async_status(self, service: str) -> Process:
        """
        Get systemd unit status. Non-blocking call.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: Process
        """
        return self.host.conn.async_run(f'systemctl status "{service}"')

    def status(self, service: str, raise_on_error: bool = True) -> ProcessResult:
        """
        Get systemd unit status. The call will wait until the operation is finished.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        return self.host.conn.run(f'systemctl status "{service}"', raise_on_error=raise_on_error)

    def async_get_property(self, service: str, prop: str) -> Process:
        """
        Get property of systemd unit. Non-blocking call.

        :param service: Unit name.
        :type service: str
        :param prop: Propery name.
        :type prop: str
        :return: Running SSH process.
        :rtype: Process
        """
        return self.host.conn.async_run(f'systemctl show "{service}" --value --property "{prop}"')

    def get_property(self, service: str, prop: str, raise_on_error: bool = True) -> str:
        """
        Get property of systemd unit. The call will wait until the operation is finished.

        :param service: Unit name.
        :type service: str
        :param prop: Propery name.
        :type prop: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: property value as string.
        :rtype: str
        """
        result = self.host.conn.run(
            f'systemctl show "{service}" --value --property "{prop}"', raise_on_error=raise_on_error
        )
        return result.stdout.strip()

    def async_reload_daemon(self) -> Process:
        """
        Reload systemd daemon to refresh unit files. Non-blocking call.

        :return: Running SSH process.
        :rtype: Process
        """
        self.logger.info("systemd: reloading systemd daemon")
        return self.host.conn.async_run("systemctl daemon-reload", log_level=ProcessLogLevel.Error)

    def reload_daemon(self, raise_on_error: bool = True) -> ProcessResult:
        """
        Reload systemd daemon to refresh unit files. The call will wait until the operation is finished.

        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: ProcessResult
        """
        return self.host.conn.run("systemctl daemon-reload", raise_on_error=raise_on_error)

    def _debug_failure(self, service: str, command: str) -> str:
        return f"{command} || ({self._query_logs_command(service)})"

    def _query_logs_command(self, service: str) -> str:
        cmds = [
            "rc=$?",
            f"echo '+ systemctl status {service}'",
            f"systemctl status {service}",
            "echo ''",
            f"echo '+ journalctl --no-pager -xeu {service}'",
            f"journalctl --no-pager -xeu {service}",
            "exit $rc",
        ]

        return ";".join(cmds)

    def __set_initial_state(self, service: str) -> None:
        if service in self.initial_states:
            return

        result = self.host.conn.run(
            f'systemctl status "{service}"', log_level=ProcessLogLevel.Silent, raise_on_error=False
        )

        if result.rc == 0 or (result.rc == 3 and "Active: activating" in result.stdout):
            self.initial_states[service] = True
        else:
            self.initial_states[service] = False
