Filesystem: Manipulating Files and Folders
##########################################

The :mod:`pytest_mh.utils.fs` module provides access to remote files and folders:
reading and writing files, creating folders, making temporary folders and files
and more.

A backup is created for every path that is changed during a test and it is
restored after the test is finished. Therefore you do not have to worry about
touching any path, the original contents and state (including ownership, mode
and context) is fully restored.

.. seealso::

    See the API reference of :class:`~pytest_mh.utils.fs.LinuxFileSystem` for
    more information.

.. note::

    Currently, we only provide :class:`~pytest_mh.utils.fs.LinuxFileSystem` to
    manipulate files and folders on Linux systems. Contributions for Windows
    world are welcomed.

.. code-block:: python
    :caption: Example: Adding fs utility to your role

    from pytest_mh import MultihostHost
    from pytest_mh.utils.fs import LinuxFileSystem

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

        self.fs: LinuxFileSystem = LinuxFileSystem(self.host)
        """
        File system manipulation.
        """

.. code-block:: python
    :caption: Example: Writing contents to a file

    @pytest.mark.topology(...)
    def test_fs(client: ClientRole):
        ...
        client.fs.write("/etc/my.conf", "configuration", mode="600")
        ...

.. code-block:: python
    :caption: Example: Writing contents to a temporary file

    @pytest.mark.topology(...)
    def test_fs(client: ClientRole):
        ...
        tmp_path = client.fs.mktmp("contents")
        ...