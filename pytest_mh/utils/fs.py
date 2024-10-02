from __future__ import annotations

import base64
import textwrap
from collections import deque
from typing import Self

from .. import MultihostHost, MultihostReentrantUtility
from ..conn import ProcessLogLevel, ProcessResult

__all__ = ["LinuxFileSystem"]


class LinuxFileSystem(MultihostReentrantUtility[MultihostHost]):
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
        self.__states: deque[tuple[list[str], dict[str, tuple[str, str]]]] = deque()
        self.__rollback: list[str] = []
        self.__backup: dict[str, tuple[str, str]] = {}

    def __enter__(self) -> Self:
        """
        Saves current state.

        :return: Self.
        :rtype: Self
        """
        self.__states.append((self.__rollback, self.__backup))
        self.__rollback = []
        self.__backup = {}

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Revert all changes done during current context.
        """
        if self.__rollback:
            self.host.logger.info(
                "Reverting file system changes",
                extra={
                    "data": {
                        "Paths": [f"{path} ({state})" for path, (_, state) in sorted(self.__backup.items())],
                    }
                },
            )

            cmd = "\n".join(reversed(self.__rollback))
            if cmd:
                self.host.conn.run(cmd, log_level=ProcessLogLevel.Error)

        self.__rollback, self.__backup = self.__states.pop()

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
        self.logger.info(f'Creating directory "{path}"')
        self.host.conn.run(
            f"""
                set -ex
                rm -fr '{path}'
                mkdir '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=ProcessLogLevel.Error,
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
        backup_exists = path in self.__backup
        self.backup(path)
        self.logger.info(f'Creating directory "{path}" (with parents)')
        result = self.host.conn.run(
            f"""
                set -ex
                rm -fr '{path}'
                mkdir -v -p '{path}' | head -1 | sed -E "s/mkdir:[^']+'(.+)'$/\\1/"
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=ProcessLogLevel.Error,
        )

        if result.stdout and result.stdout != path:
            if not backup_exists:
                action, _ = self.__backup.pop(path)
                self.__rollback.remove(action)

            action = f"rm --force --recursive '{result.stdout}'"
            self.__rollback.append(action)
            self.__backup[result.stdout] = (action, "delete")

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

        self.logger.info("Creating temporary file")
        result = self.host.conn.run(
            """
                set -ex
                tmp=`mktemp /tmp/mh.fs.rollback.XXXXXXXXX`
                echo $tmp
            """,
            log_level=ProcessLogLevel.Error,
        )

        tmpfile = result.stdout.strip()
        if not tmpfile:
            raise OSError("Temporary file was not created")

        action = f"rm --force '{tmpfile}'"
        self.__backup[tmpfile] = (action, "delete")
        self.__rollback.append(action)

        if contents is not None:
            if dedent:
                contents = textwrap.dedent(contents).strip()

            self.logger.info(f'Writing file "{tmpfile}"', extra={"data": {"Contents": contents}})
            self.host.conn.run(f"cat > '{tmpfile}'", input=contents, log_level=ProcessLogLevel.Error)

        attrs = self.__gen_chattrs(tmpfile, mode=mode, user=user, group=group)
        if attrs:
            self.host.conn.run(attrs, log_level=ProcessLogLevel.Error)

        return tmpfile

    def rm(self, path: str) -> None:
        """
        Remove remote file or directory.

        :param path: File path.
        :type path: str
        """
        self.backup(path)
        self.logger.info(f'Removing file "{path}"')

        self.host.conn.run(
            f"""
                set -ex
                rm -fr '{path}'
            """,
            log_level=ProcessLogLevel.Error,
        )

    def read(self, path: str) -> str:
        """
        Read remote file and return its contents.

        :param path: File path.
        :type path: str
        :return: File contents.
        :rtype: str
        """
        self.logger.info(f'Reading file "{path}"')
        result = self.host.conn.exec(["cat", path], log_level=ProcessLogLevel.Error)

        return result.stdout

    def exists(self, path: str) -> bool:
        """
        Checks file or directory to see if they exist.

        :param path: File path.
        :type path: str
        :return: True or False
        :rtype: bool
        """
        self.logger.info(f'Checking if "{path}" exists')
        result = self.host.conn.exec(["ls", path], log_level=ProcessLogLevel.Error, raise_on_error=False)

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
        self.logger.info(f'Writing file "{path}"', extra={"data": {"Contents": contents}})

        self.host.conn.run(
            f"""
                set -ex

                if [ -d '{path}' ]; then
                  rm -fr '{path}'
                fi

                cat > '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            input=contents,
            log_level=ProcessLogLevel.Error,
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
        self.logger.info(f'Appending to file "{path}"', extra={"data": {"Contents": contents}})

        self.host.conn.run(
            f"""
                set -ex
                cat >> '{path}'
            """,
            input=contents,
            log_level=ProcessLogLevel.Error,
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
        self.logger.info(f'Touching file "{path}"')

        self.host.conn.run(
            f"""
                set -ex
                touch '{path}'
                {self.__gen_chattrs(path, mode=mode, user=user, group=group)}
            """,
            log_level=ProcessLogLevel.Error,
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
        self.logger.info(f'Truncating file "{path}"', extra={"data": {"Size": size}})

        self.host.conn.run(
            f"""
                set -ex
                truncate -s '{size}' '{path}'
            """,
            log_level=ProcessLogLevel.Error,
        )

    def copy(
        self,
        srcpath: str,
        dstpath: str,
        *,
        mode: str | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """
        Copy a remote file @srcpath to remote @dstpath.

        :param srcpath: Remote source file path.
        :type srcpath: str
        :param dstpath: Remote destination file path.
        :type dstpath: str
        :param mode: Access mode (chmod value), defaults to None
        :type mode: str | None, optional
        :param user: Owner, defaults to None
        :type user: str | None, optional
        :param group: Group, defaults to None
        :type group: str | None, optional
        :param dedent: Automatically dedent and strip file contents, defaults to True
        :type dedent: bool, optional
        """
        self.backup(dstpath)
        self.logger.info(f'Copying file "{srcpath}" to "{dstpath}"')

        self.host.conn.run(
            f"""
                set -ex
                cp --archive '{srcpath}' '{dstpath}'
                {self.__gen_chattrs(dstpath, mode=mode, user=user, group=group)}
            """,
            log_level=ProcessLogLevel.Error,
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

        self.host.conn.run(
            f"""
                set -ex

                if [ -d '{remote_path}' ]; then
                  rm -fr '{remote_path}'
                fi

                base64 --decode > '{remote_path}'
                {self.__gen_chattrs(remote_path, mode=mode, user=user, group=group)}
            """,
            input=encoded,
            log_level=ProcessLogLevel.Error,
        )

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

        self.host.conn.run(f"base64 --decode > '{tmp_path}'", input=encoded, log_level=ProcessLogLevel.Error)

        return tmp_path

    def download(self, remote_path: str, local_path: str) -> None:
        """
        Download file from remote host to local machine.

        :param remote_path: Remote path.
        :type remote_path: str
        :param local_path: Local path.
        :type local_path: str
        """
        self.logger.info(f'Downloading file "{self.host.hostname}:{remote_path}" to "{local_path}"')
        result = self.host.conn.exec(["base64", remote_path], log_level=ProcessLogLevel.Error)
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
        result = self.host.conn.run(
            f"""
            tmp=`mktemp /tmp/mh.fs.download_files.XXXXXXXXX`
            tar -czvf "$tmp" {' '.join([f'$(compgen -G "{path}")' for path in paths])} &> /dev/null
            base64 "$tmp"
            rm -f "$tmp" &> /dev/null
        """,
            log_level=ProcessLogLevel.Error,
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

        self.logger.info(f'Creating a backup of "{path}"')
        result = self.host.conn.run(
            f"""
        set -ex

        if [ -f '{path}' ]; then
            tmp=`mktemp /tmp/mh.fs.rollback.XXXXXXXXX`
            cp --force --archive '{path}' "$tmp"
            echo "cp --force --archive '$tmp' '{path}' && rm --force '$tmp'"
            echo "restore file"
        elif [ -d '{path}' ]; then
            tmp=`mktemp -d /tmp/mh.fs.rollback.XXXXXXXXX`
            cp --force --archive '{path}/.' "$tmp"
            echo "rm --force --recursive '{path}' && mv --force '$tmp' '{path}'"
            echo "restore directory"
        elif [ ! -d '{path}' ] && [ ! -f '{path}' ]; then
            echo "rm --force --recursive '{path}'"
            echo "delete"
        fi
        """,
            log_level=ProcessLogLevel.Error,
        )

        action = result.stdout_lines[-2]
        state = result.stdout_lines[-1]

        self.__rollback.append(action)
        self.__backup[path] = (action, state)
        return state != "delete"

    def restore(self, path: str) -> bool:
        """
        Restore file or directory from previous backup.

        .. note::
            It is also possible that the file or directory does not exist. In
            that case, the path is removed to remove any file or directory that
            might have been created.

        :param path: Path to restore.
        :type path: str
        :return: True if the backup of path exists and it was restored, False otherwise.
        :rtype: bool
        """
        item = self.__backup.get(path)
        if item is None:
            # Backup is not present
            return False

        action, state = item

        self.logger.info(f'Restoring "{path}" from backup ({state})')
        self.host.conn.run(action, log_level=ProcessLogLevel.Error)

        self.__rollback.remove(action)
        del self.__backup[path]

        return True

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
    ) -> ProcessResult:
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
        :rtype: ProcessResult
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

        return self.host.conn.exec(["wc", *args, file], log_level=ProcessLogLevel.Error)

    def diff(
        self,
        path1: str,
        path2: str,
        *,
        brief: bool = False,
        recursive: bool = False,
        ignore_case: bool = False,
        args: list[str] | None = None,
    ) -> ProcessResult:
        """
        Compare files line by line.
        Exit status is 0 if inputs are the same, 1 if different, 2 if trouble.

        :param path1: Path to file or directory to be compared
        :type path1: str
        :param path2: Path to file or directory to be compared
        :type path2: str
        :param brief: Report only when files differ, but do not print the diff itself, defaults to False
        :type brief: bool, optional
        :param recursive: Recursively compare any subdirectories found, defaults to False
        :type recursive: bool, optional
        :param ignore_case: Ignore case differences in file contents, defaults to False
        :type ignore_case: bool, optional
        :param args: Additional options, defaults to None
        :type args: list[str] | None, optional
        :return: Result of process
        :rtype: ProcessResult
        """
        args = args if args else []
        if brief:
            args.append("--brief")
        if recursive:
            args.append("--recursive")
        if ignore_case:
            args.append("--ignore-case")

        return self.host.conn.exec(["diff", *args, path1, path2], raise_on_error=False)

    def chmod(self, mode: str, path: str, args: list[str] | None = None) -> ProcessResult:
        """
        Change file/folder mode bits.
        Mode can be specified in two ways: octal number e.g. "666", "444" or
        a symbolic representation of changes e.g. "u=rw,go=r", "go-rw"

        :param mode: New mode of file/folder
        :type mode: str
        :param path: File or folder whose permissions change
        :type path: str
        :param args: Additional options, defaults to None
        :type args: list[str] | None, optional
        :return: Result of process
        :rtype: ProcessResult
        """
        self.backup(path)
        self.logger.info(f'Changing mode to "{mode}" for "{path}"')
        args = args if args else []
        return self.host.conn.exec(["chmod", *args, mode, path], log_level=ProcessLogLevel.Error)

    def chown(
        self, path: str, user: str | None = None, group: str | None = None, args: list[str] | None = None
    ) -> ProcessResult:
        """
        Change file owner and group.

        :param path: Path to file
        :type path: str
        :param user: New file owner, if None then user remains same, defaults to None
        :type user: str | None, optional
        :param group: New file group, if None then group remains same, defaults to None
        :type group: str | None, optional
        :param args: Additional options, defaults to None
        :type args: list[str] | None, optional
        :return: Result of process
        :rtype: ProcessResult
        """
        self.backup(path)
        if user:
            self.logger.info(f'Changing owner of "{path}" to "{user}"')
        if group:
            self.logger.info(f'Changing group of "{path}" to "{group}"')

        args = args if args else []
        mode = f"{user}" if user else ""
        mode += f":{group}" if group else ""
        return self.host.conn.exec(["chown", mode, *path.split(), *args], log_level=ProcessLogLevel.Error)

    def sed(self, command: str, path: str, args: list[str] | None = None) -> ProcessResult:
        """
        SED command in UNIX stands for stream editor and it can perform lots of
        functions on file like searching, find and replace, insertion or deletion.

        :param command: Sed command
        :type command: str
        :param path: File where changes will happen
        :type path: str
        :param args: Additional options, defaults to None
        :type args: list[str] | None, optional
        :return: Result of process
        :rtype: ProcessResult
        """
        self.backup(path)
        self.logger.info(f"Running sed {command} on {path}")
        args = args if args else []
        return self.host.conn.exec(["sed", *args, command, path], log_level=ProcessLogLevel.Error)
