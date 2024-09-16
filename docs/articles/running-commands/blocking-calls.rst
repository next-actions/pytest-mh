Blocking Calls
##############

It is possible to run a command using a blocking code, meaning the code will
block until the command is finished and its result is returned. The result is
instance of :class:`~pytest_mh.conn.ProcessResult` and gives you access to
return code, standard output and standard error output.

.. code-block:: python
    :caption: Example: Blocking call

    from pytest_mh import MultihostHost
    from pytest_mh.conn import ProcessResult

    class ExampleRole(MultihostHost[ExampleDomain]):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

        def say_hello(self) -> ProcessResult:
            """
            Run a single line script code.
            """
            return self.host.conn.run("echo 'Hello World'")

        def say_hello_argv(self) -> ProcessResult:
            """
            Execute command by passing list of arguments.
            """
            return self.host.conn.exec(["echo", "Hello World"])

        def say_script(self) -> ProcessResult:
            """
            Execute a multiline script code.
            """
            return self.host.conn.run(
                """
                set -ex

                echo 'Hello World'
                """
            )

        def say_hello_cat(self) -> ProcessResult:
            """
            You can also pass input data.
            """
            return self.host.conn.run("cat", input="Hello World")

    @pytest.mark.topology(...)
    def test_hello(example: ExampleRole) -> None:
        result = example.say_hello()
        assert result.stdout == "Hello World"

        result = example.say_hello_argv()
        assert result.stdout == "Hello World"

        result = example.say_hello_script()
        assert result.stdout == "Hello World"

        result = example.say_hello_cat()
        assert result.stdout == "Hello World"

If the command returns a non-zero return code, it is automatically considered a
failure and :class:`~pytest_mh.conn.ProcessError` is raised. If you don't want
to raise the error or if you want to raise it on different condition, you can
overwrite the behaviour with ``raise_on_error`` argument.

.. code-block:: python
    :caption: Example: Do not raise exception on non-zero return code

    result = self.host.conn.run("echo 'Hello World'", raise_on_error=False)
    if result.rc not in (0, 1):
        # Raise ProcessError if rc was not 0 or 1
        result.throw()

.. note::

    Each command execution is logged in the pytest-mh logger. This can often
    pollute the logs with a lot of commands whose output result is only really
    important if it fails. Therefore, you can change the log level to add a log
    record only if the command yields a non-zero return code.

    .. code-block:: python
        :caption: Example: Custom log level

        self.host.conn.run(
            "echo 'Hello World'",
            log_level=ProcessLogLevel.Error
        )

    See :class:`~pytest_mh.conn.ProcessLogLevel` for all available log levels.
