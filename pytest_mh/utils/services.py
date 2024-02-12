from __future__ import annotations

from .. import MultihostHost, MultihostUtility
from ..ssh import SSHLog, SSHProcess, SSHProcessResult

__all__ = ["SystemdServices"]


class SystemdServices(MultihostUtility):
    """
    Manage remote services.
    """

    def __init__(self, host: MultihostHost) -> None:
        super().__init__(host)
        self.initial_states: dict[str, bool] = {}

    def teardown(self) -> None:
        # Restart all services that were touched
        self.reload_daemon()
        for service, state in self.initial_states.items():
            self.host.ssh.run(
                f'systemctl stop "{service}" || systemctl status "{service}"',
                raise_on_error=False,
                log_level=SSHLog.Error,
            )
            if state:
                self.host.ssh.run(
                    f'systemctl start "{service}" || systemctl status "{service}"',
                    raise_on_error=False,
                    log_level=SSHLog.Error,
                )

    def async_start(self, service: str) -> SSHProcess:
        """
        Start a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be started. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: starting "{service}" asynchronously')
        return self.host.ssh.async_run(
            f'systemctl reset-failed "{service}"; systemctl start "{service}" || systemctl status "{service}"',
            log_level=SSHLog.Error,
        )

    def start(self, service: str, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Start a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be started. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: starting "{service}"')
        return self.host.ssh.run(
            f'systemctl reset-failed "{service}"; systemctl start "{service}" || systemctl status "{service}"',
            raise_on_error=raise_on_error,
            log_level=SSHLog.Error,
        )

    def async_stop(self, service: str) -> SSHProcess:
        """
        Stop a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be stopped. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: stopping "{service}" asynchronously')
        return self.host.ssh.async_run(
            f'systemctl stop "{service}" || systemctl status "{service}"', log_level=SSHLog.Error
        )

    def stop(self, service: str, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Stop a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be stoped. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: stopping "{service}"')
        return self.host.ssh.run(
            f'systemctl stop "{service}" || systemctl status "{service}"',
            raise_on_error=raise_on_error,
            log_level=SSHLog.Error,
        )

    def async_restart(self, service: str) -> SSHProcess:
        """
        Restart a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be restarted. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: restarting "{service}" asynchronously')
        return self.host.ssh.async_run(
            f'systemctl reset-failed "{service}"; systemctl restart "{service}" || systemctl status "{service}"',
            log_level=SSHLog.Error,
        )

    def restart(self, service: str, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Restart a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be restarted. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        self.__set_initial_state(service)
        self.logger.info(f'systemd: restarting "{service}"')
        return self.host.ssh.run(
            f'systemctl reset-failed "{service}"; systemctl restart "{service}" || systemctl status "{service}"',
            raise_on_error=raise_on_error,
            log_level=SSHLog.Error,
        )

    def async_reload(self, service: str) -> SSHProcess:
        """
        Reload a systemd unit. Non-blocking call.

        ``systemctl status $unit`` is called automatically if the unit can not
        be reloaded. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        self.logger.info(f'systemd: reloading "{service}" asynchronously')
        return self.host.ssh.async_run(
            f'systemctl reload "{service}" || systemctl status "{service}"', log_level=SSHLog.Error
        )

    def reload(self, service: str, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Reload a systemd unit. The call will wait until the operation is finished.

        ``systemctl status $unit`` is called automatically if the unit can not
        be reloaded. The status is then visible in the logs.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        self.logger.info(f'systemd: reloading "{service}"')
        return self.host.ssh.run(
            f'systemctl reload "{service}" || systemctl status "{service}"',
            raise_on_error=raise_on_error,
            log_level=SSHLog.Error,
        )

    def async_status(self, service: str) -> SSHProcess:
        """
        Get systemd unit status. Non-blocking call.

        :param service: Unit name.
        :type service: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        return self.host.ssh.async_run(f'systemctl status "{service}"')

    def status(self, service: str, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Get systemd unit status. The call will wait until the operation is finished.

        :param service: Unit name.
        :type service: str
        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        return self.host.ssh.run(f'systemctl status "{service}"', raise_on_error=raise_on_error)

    def async_get_property(self, service: str, prop: str) -> SSHProcess:
        """
        Get property of systemd unit. Non-blocking call.

        :param service: Unit name.
        :type service: str
        :param prop: Propery name.
        :type prop: str
        :return: Running SSH process.
        :rtype: SSHProcess
        """
        return self.host.ssh.async_run(f'systemctl show "{service}" --value --property "{prop}"')

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
        result = self.host.ssh.run(
            f'systemctl show "{service}" --value --property "{prop}"', raise_on_error=raise_on_error
        )
        return result.stdout.strip()

    def async_reload_daemon(self) -> SSHProcess:
        """
        Reload systemd daemon to refresh unit files. Non-blocking call.

        :return: Running SSH process.
        :rtype: SSHProcess
        """
        self.logger.info("systemd: reloading systemd daemon")
        return self.host.ssh.async_run("systemctl daemon-reload", log_level=SSHLog.Error)

    def reload_daemon(self, raise_on_error: bool = True) -> SSHProcessResult:
        """
        Reload systemd daemon to refresh unit files. The call will wait until the operation is finished.

        :param raise_on_error: Raise exception on error, defaults to True
        :type raise_on_error: bool, optional
        :return: SSH process result.
        :rtype: SSHProcessResult
        """
        return self.host.ssh.run("systemctl daemon-reload", raise_on_error=raise_on_error)

    def __set_initial_state(self, service: str) -> None:
        if service in self.initial_states:
            return

        result = self.host.ssh.run(f'systemctl status "{service}"', log_level=SSHLog.Silent, raise_on_error=False)
        self.initial_states[service] = result.rc == 0
