from __future__ import annotations

import base64
import textwrap

from .. import MultihostHost, MultihostUtility
from ..ssh import SSHLog, SSHProcessResult

__all__ = ["LinuxFileSystem"]


class LinuxFileSystem(MultihostUtility):
    """
    Perform file system operations on remote host.

    All changes are automatically reverted when a test is finished.
    """

    def __init__(self, host: MultihostHost) -> None:
        """
        :param host: Remote host instance.
        :type host: MultihostHost
        """
        super().__init__(host)
        self.__rollback: list[str] = []
        self.__backup: dict[str, bool] = {}

    def teardown(self):
        """
        Revert all file system changes.

        :meta private:
        """
        cmd = "\n".join(reversed(self.__rollback))
        if cmd:
            self.host.ssh.run(cmd)

        super().teardown()

    def mkdir(self, path: str, *, mode: str | None = None, user: str | None = None, group: str | None = None) -> None:
        """
        Create directory on remote host.

        :param path: Path of the directory.
        :type path: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        """
        self.backup(path)
        self.logger.info(f'Creating directory "{path}" on {self.host.hostname}')
        self.host.ssh.run(
            f"""
                set -ex
                rm -fr '{path}'
                mkdir '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=SSHLog.Error,
        )

    def mkdir_p(
        self, path: str, *, mode: str | None = None, user: str | None = None, group: str | None = None
    ) -> None:
        """
        Create directory on remote host, including all missing parent directories.

        :param path: Path of the directory.
        :type path: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        """
        self.backup(path)
        self.logger.info(f'Creating directory "{path}" (with parents) on {self.host.hostname}')
        result = self.host.ssh.run(
            f"""
                set -ex
                rm -fr '{path}'
                mkdir -v -p '{path}' | head -1 | sed -E "s/mkdir:[^']+'(.+)'$/\\1/"
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=SSHLog.Error,
        )

        if result.stdout:
            self.__rollback.append(f"rm --force --recursive '{result.stdout}'")

    def mktmp(
        self,
        contents: str | None = None,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
        dedent: bool = True,
    ) -> str:
        """
        Create temporary file on remote host.

        :param contents: File contents to write.
        :type contents: str | None
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        :param dedent: Automatically dedent and strip file contents, defaults to True
        :type dedent: bool, optional
        :raises OSError: If the file can not be created.
        :return: Temporary file path.
        :rtype: str
        """

        self.logger.info(f"Creating temporary file on {self.host.hostname}")
        result = self.host.ssh.run(
            """
                set -ex
                tmp=`mktemp /tmp/mh.fs.rollback.XXXXXXXXX`
                echo $tmp
            """,
            log_level=SSHLog.Error,
        )

        tmpfile = result.stdout.strip()
        if not tmpfile:
            raise OSError("Temporary file was not created")

        self.__rollback.append(f"rm --force '{tmpfile}'")

        if contents is not None:
            if dedent:
                contents = textwrap.dedent(contents).strip()

            self.logger.info(
                f'Writing file "{tmpfile}" on {self.host.hostname}', extra={"data": {"Contents": contents}}
            )
            self.host.ssh.run(f"cat > '{tmpfile}'", input=contents, log_level=SSHLog.Error)

        attrs = self.__gen_chattrs(tmpfile, mode=mode, user=user, group=group)
        if attrs:
            self.host.ssh.run(attrs, log_level=SSHLog.Error)

        return tmpfile

    def read(self, path: str) -> str:
        """
        Read remote file and return its contents.

        :param path: File path.
        :type path: str
        :return: File contents.
        :rtype: str
        """
        self.logger.info(f'Reading file "{path}" on {self.host.hostname}')
        result = self.host.ssh.exec(["cat", path], log_level=SSHLog.Error)

        return result.stdout

    def exists(self, path: str) -> bool:
        """
        Checks file or directory to see if they exist.

        :param path: File path.
        :type path: str
        :return: True or False
        :rtype: bool
        """
        self.logger.info(f'Checking "{path}" exists on {self.host.hostname}')
        result = self.host.ssh.exec(["ls", path], log_level=SSHLog.Error, raise_on_error=False)

        if result.rc == 0:
            return True

        return False

    def write(
        self,
        path: str,
        contents: str,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
        dedent: bool = True,
    ) -> None:
        """
        Write to a remote file.

        :param path: File path.
        :type path: str
        :param contents: File contents to write.
        :type contents: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        :param dedent: Automatically dedent and strip file contents, defaults to True
        :type dedent: bool, optional
        """
        if dedent:
            contents = textwrap.dedent(contents).strip()

        self.backup(path)
        self.logger.info(f'Writing file "{path}" on {self.host.hostname}', extra={"data": {"Contents": contents}})

        self.host.ssh.run(
            f"""
                set -ex
                rm -fr '{path}'
                cat > '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            input=contents,
            log_level=SSHLog.Error,
        )

    def append(
        self,
        path: str,
        contents: str,
        *,
        dedent: bool = True,
    ) -> None:
        """
        Append to a remote file.

        :param path: File path.
        :type path: str
        :param contents: File contents to write.
        :type contents: str
        :param dedent: Automatically dedent and strip file contents, defaults to True
        :type dedent: bool, optional
        """
        if dedent:
            contents = textwrap.dedent(contents).strip()

        self.backup(path)
        self.logger.info(f'Appending to file "{path}" on {self.host.hostname}', extra={"data": {"Contents": contents}})

        self.host.ssh.run(
            f"""
                set -ex
                cat >> '{path}'
            """,
            input=contents,
            log_level=SSHLog.Error,
        )

    def touch(
        self,
        path: str,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """
        Touch a remote file.

        :param path: File path.
        :type path: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        :param dedent: Automatically dedent and strip file contents, defaults to True
        :type dedent: bool, optional
        """
        self.backup(path)
        self.logger.info(f'Touching file "{path}" on {self.host.hostname}')

        self.host.ssh.run(
            f"""
                set -ex
                touch '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=SSHLog.Error,
        )

    def truncate(
        self,
        path: str,
        *,
        size: int = 0,
    ) -> None:
        """
        Truncate remote file.

        :param path: File path.
        :type path: str
        :param size: Target file size, defaults to 0
        :type size: int, optional
        """
        self.backup(path)
        self.logger.info(f'Truncating file "{path}" on {self.host.hostname}', extra={"data": {"Size": size}})

        self.host.ssh.run(
            f"""
                set -ex
                truncate -s '{size}' '{path}'
            """,
            log_level=SSHLog.Error,
        )

    def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """
        Upload local file.

        :param local_path: Source local path.
        :type local_path: str
        :param remote_path: Destination remote path.
        :type remote_path: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        """
        self.backup(remote_path)
        self.logger.info(f'Uploading file "{local_path}" to "{self.host.hostname}:{remote_path}"')
        with open(local_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        self.host.ssh.run(
            f"""
                set -ex
                rm -fr '{remote_path}'
                base64 --decode > '{remote_path}'
                {self.__gen_chattrs(remote_path, mode=mode, user=user, group=group)}
            """,
            input=encoded,
            log_level=SSHLog.Error,
        )
        self.__rollback.append(f"rm --force '{remote_path}'")

    def upload_to_tmp(
        self,
        local_path: str,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> str:
        """
        Upload local file to a new temporary file on remote host.

        :param local_path: Source local path.
        :type local_path: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        :return: Temporary file path.
        :rtype: str
        """
        tmp_path = self.mktmp(mode=mode, user=user, group=group)

        self.logger.info(f'Uploading file "{local_path}" to "{self.host.hostname}:{tmp_path}"')
        with open(local_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        self.host.ssh.run(f"base64 --decode > '{tmp_path}'", input=encoded, log_level=SSHLog.Error)

        return tmp_path

    def download(self, remote_path: str, local_path: str) -> None:
        """
        Download file from remote host to local machine.

        :param remote_path: Remote path.
        :type remote_path: str
        :param local_path: Local path.
        :type local_path: str
        """
        self.logger.info(f'Downloading file "{remote_path}" from {self.host.hostname} to "{local_path}"')
        result = self.host.ssh.exec(["base64", remote_path], log_level=SSHLog.Error)
        with open(local_path, "wb") as f:
            f.write(base64.b64decode(result.stdout))

    def download_files(self, paths: list[str], local_path: str) -> None:
        """
        Download multiple files from remote host. The files are stored in single
        gzipped tarball on the local machine. The remote file path may contain
        glob pattern.

        :param paths: List of remote file paths. May contain glob pattern.
        :type paths: list[str]
        :param local_path: Path to the gzipped tarball destination file on local machine.
        :type local_path: str
        """
        self.logger.info(
            f'Downloading files from {self.host.hostname} to "{local_path}"', extra={"data": {"Paths": paths}}
        )
        result = self.host.ssh.run(
            f"""
            tmp=`mktemp /tmp/mh.fs.download_files.XXXXXXXXX`
            tar -czvf "$tmp" {' '.join([f'$(compgen -G "{path}")' for path in paths])} &> /dev/null
            base64 "$tmp"
            rm -f "$tmp" &> /dev/null
        """,
            log_level=SSHLog.Error,
        )

        with open(local_path, "wb") as f:
            f.write(base64.b64decode(result.stdout))

    def backup(self, path: str) -> bool:
        """
        Backup file or directory.

        The path is automatically restored from the backup when a test is
        finished.

        .. note::
            It is also possible that the file or directory does not exist. In
            that case, the path is removed during the teardown process to
            remove any file or directory that might have been created.

        :param path: Path to back up.
        :type path: str
        :return: True if the path exists and backup was done, False otherwise.
        :rtype: bool
        """
        if path in self.__backup:
            # Backup is already present
            return True

        self.logger.info(f'Creating a backup of "{path}" on {self.host.hostname}')
        result = self.host.ssh.run(
            f"""
        set -ex

        if [ -f '{path}' ]; then
            tmp=`mktemp /tmp/mh.fs.rollback.XXXXXXXXX`
            cp --force --archive '{path}' "$tmp"
            echo "mv --force '$tmp' '{path}'"
        elif [ -d '{path}' ]; then
            tmp=`mktemp -d /tmp/mh.fs.rollback.XXXXXXXXX`
            cp --force --archive '{path}/.' "$tmp"
            echo "rm --force --recursive '{path}' && mv --force '$tmp' '{path}'"
        elif [ ! -d '{path}' ] && [ ! -f '{path}' ]; then
            echo "rm --force --recursive '{path}'"
        fi
        """,
            log_level=SSHLog.Error,
        )

        action = result.stdout.strip()
        if action:
            self.__rollback.append(action)
            self.__backup[path] = True
            return True

        return False

    def __gen_chattrs(
        self, path: str, *, mode: str | None = None, user: str | None = None, group: str | None = None
    ) -> str:
        cmds = []
        if mode is not None:
            cmds.append(f"chmod '{mode}' '{path}'")

        if user is not None:
            cmds.append(f"chown '{user}' '{path}'")

        if group is not None:
            cmds.append(f"chgrp '{group}' '{path}'")

        return " && ".join(cmds)

    def wc(
        self, file: str, lines: bool = False, word: bool = False, bytes: bool = False, chars: bool = False
    ) -> SSHProcessResult:
        """
        Print newline, word, and byte counts for specific file.

        Output example without additional arguments: ``67 564 3514 file_name``

        :param file: File whose content is counted
        :type file: str
        :param lines: Print the newline counts, defaults to False
        :type lines: bool, optional
        :param word: Print the word counts, defaults to False
        :type word: bool, optional
        :param bytes: Print the byte counts, defaults to False
        :type bytes: bool, optional
        :param chars: Print the character counts, defaults to False
        :type chars: bool, optional
        :return: Result of process
        :rtype: SSHProcessResult
        """
        args = []
        if lines:
            args.append("-l")

        if word:
            args.append("-w")

        if bytes:
            args.append("-b")

        if chars:
            args.append("-m")

        return self.host.ssh.exec(["wc", *args, file])
