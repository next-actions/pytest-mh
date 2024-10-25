Building command line
#####################

Pytest-mh provides a built in :class:`~pytest_mh.cli.CLIBuilder` class that
helps with constructing a command line for execution, especially when using
optional values since it can easily skip parameters that are set to ``None``.
There are three methods available within the class:

* :meth:`~pytest_mh.cli.CLIBuilder.command`
* :meth:`~pytest_mh.cli.CLIBuilder.argv`
* :meth:`~pytest_mh.cli.CLIBuilder.args`

:meth:`~pytest_mh.cli.CLIBuilder.args` processes the arguments, combines them
with given values and returns the command line as a list.
:meth:`~pytest_mh.cli.CLIBuilder.argv` works in the same way, but it returns the
full ``argv`` list (including the command name) that is ready to be executed
with :meth:`~pytest_mh.conn.Connection.exec` and finally
:meth:`~pytest_mh.cli.CLIBuilder.command` returns a string that can be passed
directly to :meth:`~pytest_mh.conn.Connection.run`.

All methods take a dictionary, where key is the parameter name and value is a
tuple of parameter type and its value. The parameter type is one of
:class:`CLIBuilder.option <pytest_mh.cli.CLIBuilder.option>` value that can
differentiate between positional, key-value or switch argument. This dictionary
is then consumed by one of the methods, if a parameter value inside the tuple is
``None`` then this parameter is omitted.

.. code-block:: python
    :caption: Example of CLIBuilder.command

    cli = CLIBuilder(Bash())
    args: CLIBuilderArgs = {
        "password": (cli.option.VALUE, None),     # None values are ignored
        "home": (cli.option.VALUE, "/home/jdoe"), # --home '/home/jdoe'
        "enabled": (cli.option.SWITCH, True),     # --enabled
        "login": (cli.option.POSITIONAL, "jdoe"), # 'jdoe'
    }

    line = cli.command("add-user", args)
    # add-user --home '/home/jdoe' --enabled 'jdoe'

.. code-block:: python
    :caption: Example of CLIBuilder.argv

    cli = CLIBuilder(Bash())
    args: CLIBuilderArgs = {
        "password": (cli.option.VALUE, None),     # None values are ignored
        "home": (cli.option.VALUE, "/home/jdoe"), # --home '/home/jdoe'
        "enabled": (cli.option.SWITCH, True),     # --enabled
        "login": (cli.option.POSITIONAL, "jdoe"), # 'jdoe'
    }

    line = cli.argv("add-user", args)
    # ["add-user", "--home", "/home/jdoe", "--enabled", "jdoe"]

.. code-block:: python
    :caption: Example of CLIBuilder.args

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

.. note::

    There is also :attr:`CLIBuilder.option.PLAIN
    <pytest_mh.cli.CLIBuilder.option.PLAIN>`. This option behaves similarly to
    :attr:`CLIBuilder.option.VALUE
    <pytest_mh.cli.CLIBuilder.option.VALUE>` but it does not quote the
    value (if quoting is enabled -- which is the default behavior of
    :meth:`~pytest_mh.cli.CLIBuilder.command`), it just adds the value to the
    position as is.

    .. code-block:: python
        :caption: Example of CLIBuilder.option.PLAIN

        cli = CLIBuilder(Bash())
        args: CLIBuilderArgs = {
            "password": (cli.option.PLAIN, "`encrypt-password 123456`"), # use value as-is
            "home": (cli.option.VALUE, "/home/jdoe"),                    # --home '/home/jdoe'
            "enabled": (cli.option.SWITCH, True),                        # --enabled
            "login": (cli.option.POSITIONAL, "jdoe"),                    # 'jdoe'
        }

        line = cli.command("add-user", args)
        # add-user --password `encrypt-password 123456` --home '/home/jdoe' --enabled 'jdoe'

