Timeouts
########

By default, all command timeout in 300 seconds, which should be more then
sufficient for most use cases. This timeout ensures that code that runs
unexpectedly long time (for example an unexpected user input is requested) is
terminated gracefully. A command that hits the timeout raises
:class:`~pytest_mh.conn.ProcessTimeoutError`.

The default timeout can be overridden on multiple places:

* Per host, in a configuration file, by setting ``timeout`` field in the
  ``host.conn`` section
* In a blocking calls using the ``timeout`` parameter, see
  :meth:`~pytest_mh.conn.Connection.run` and
  :meth:`~pytest_mh.conn.Connection.exec`
* In a non-blocking calls using the ``timeout`` parameter on the
  :meth:`~pytest_mh.conn.Process.wait` method of a running process creating by
  :meth:`~pytest_mh.conn.Connection.async_run` or
  :meth:`~pytest_mh.conn.Connection.async_exec`

.. code-block:: yaml
    :caption: Example: Overriding default timeout for the host

    hosts:
    - hostname: client1.test
      role: client
      conn:
        type: ssh
        host: 192.168.0.10
        user: root
        password: Secret123
        timeout: 600 # setting default timeout to 10 minutes

.. code-block:: python
    :caption: Example: Setting specific timeout for single command

    @pytest.mark.topology(KnownTopology.Client)
    def test_timeout(client: Client):
        result = client.host.conn.run(
            """
            echo 'stdout before';
            >&2 echo 'stderr before';
            sleep 15;
            echo 'stdout after';
            >&2 echo 'stderr after'
            """,
            timeout=5,
        )


    @pytest.mark.topology(KnownTopology.Client)
    def test_timeout_async(client: Client):
        process = client.host.conn.async_run(
            """
            echo 'stdout before';
            >&2 echo 'stderr before';
            sleep 15;
            echo 'stdout after';
            >&2 echo 'stderr after'
            """
        )

        process.wait(timeout=5)
