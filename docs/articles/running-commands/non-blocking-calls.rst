Non-Blocking Calls
##################

It is possible to run a command using a non-blocking code. This gives you more
fine grained control over the input and output. Similarly to blocking code,
there are :meth:`~pytest_mh.conn.Connection.async_run` and
:meth:`~pytest_mh.conn.Connection.async_exec` methods.

These methods return an instance of :class:`~pytest_mh.conn.Connection.Process`
which represents a running process. You can write to
:attr:`~pytest_mh.conn.Process.stdin` or iterate over
:attr:`~pytest_mh.conn.Process.stdout` and
:attr:`~pytest_mh.conn.Process.stderr` which are line-based generators.

.. warning::

    Both :attr:`~pytest_mh.conn.Process.stdout` and
    :attr:`~pytest_mh.conn.Process.stderr` read the process outputs line by
    line, therefore they will block until a full line is read.

    This is especially a problem in the executed program prompts for input. It
    is better to use :meth:`~pytest_mh.conn.Connection.expect` or
    :meth:`~pytest_mh.conn.Connection.expect_nobody` for interactive programs.

.. code-block:: python
    :caption: Example: Non-Blocking call

    from pytest_mh import MultihostHost
    from pytest_mh.conn import ProcessResult

    @pytest.mark.topology(...)
    def test_hello(example: ExampleRole) -> None:
        process = example.conn.async_run("cat")

        process.stdin.write("Hello\n")
        assert next(process.stdout) == "Hello"

        process.stdin.write("World\n")
        assert next(process.stdout) == "World"

        result = process.wait()
