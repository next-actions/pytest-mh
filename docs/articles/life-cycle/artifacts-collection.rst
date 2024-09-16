Artifacts Collection
####################

Collecting logs and other artifacts from a test is a very important task,
especially if the test fails. Most of the test frameworks allows you to collect
artifacts that are explicitly configured. Pytest-mh has this feature as well but
it also takes this a step further and allows you to collect and even produce
artifacts dynamically after a test is finished.

This is especially useful if you do not want to rely on each test to produce
artifacts that require additional commands to be run (for example a database
dump). With pytest-mh, it is possible to implement this on a different level and
therefore each test can focus solely on testing functionality, pytest-mh will
take care of producing and collecting the extra artifacts.

.. seealso::

    This feature is used to capture AVC denials and coredumps in
    :class:`~pytest_mh.utils.auditd.Auditd` and
    :class:`~pytest_mh.utils.coredumpd.Coredumpd`. You can check out the source
    code to get some examples.

    .. dropdown:: Example source code
        :color: primary
        :icon: code

        .. tab-set::

            .. tab-item:: Auditd utility

                .. literalinclude:: ../../../pytest_mh/utils/auditd.py
                    :caption: Setting artifacts in __init__
                    :pyobject: Auditd.__init__

            .. tab-item:: Coredumpd utility

                .. literalinclude:: ../../../pytest_mh/utils/coredumpd.py
                    :caption: Dynamic artifacts in get_artifacts_list()
                    :pyobject: Coredumpd.get_artifacts_list

User-defined artifacts
======================

The pytest-mh configuration file has a field ``artifacts`` in the host section
where it is possible to define a list of artifacts that should be automatically
downloaded from a host when a test is finished and before teardown is executed.
This list can also contain a wildcard.

.. code-block:: yaml
    :caption: User-defined artifact in mhc.yaml

    - hostname: client.test
      role: client
      artifacts:
      - /etc/myapp/myapp.conf
      - /var/lib/myapp/db/*
      - /var/log/myapp/*

Dynamic artifacts
=================

Dynamic artifacts are not defined in the configuration file, but are defined in
the code and therefore the list of artifacts does not have to be static but can
be dynamically extended.

Dynamic artifacts can be defined in :class:`~pytest_mh.MultihostHost`,
:class:`~pytest_mh.MultihostRole`, :class:`~pytest_mh.MultihostUtility` and
:class:`~pytest_mh.TopologyController` by adding items to the ``artifacts``
attribute of the class.

.. seealso::

    The type of the ``artifacts`` attribute is slightly more complex for hosts
    and topology controller since the artifacts can be collected on multiple
    phases for these objects. Definition of the attribute can be found here:

    * :attr:`pytest_mh.MultihostHost.artifacts`
    * :attr:`pytest_mh.MultihostRole.artifacts`
    * :attr:`pytest_mh.MultihostUtility.artifacts`
    * :attr:`pytest_mh.TopologyController.artifacts`

New artifacts can also be produced when a test is finished, or the list of
artifacts can be set more dynamically based on your own conditions (e.g.
installation failed). To achieve this, it is possible to override
``get_artifacts_list()`` method of each class. This method is used by pytest-mh
to obtain the list of artifacts to collect and it must return a ``set()`` of
artifacts.

.. seealso::

    You can find definition of ``get_artifacts_list()`` here:

    * :meth:`pytest_mh.MultihostHost.get_artifacts_list`
    * :meth:`pytest_mh.MultihostRole.get_artifacts_list`
    * :meth:`pytest_mh.MultihostUtility.get_artifacts_list`
    * :meth:`pytest_mh.TopologyController.get_artifacts_list`

.. warning::

    The default implementation of ``get_artifacts_list()`` simply returns
    ``self.artifacts``. It is not mandatory to reference this attribute in any
    way in your implementation, but keep in mind that then this attribute will
    not have any effect.

.. literalinclude:: ../../../pytest_mh/_private/multihost.py
    :caption: get_artifacts_list() default implementation
    :pyobject: MultihostRole.get_artifacts_list

The ``get_artifacts_list()`` method takes two arguments:

* ``host`` which is the host where the artifacts will be collected. This does
  not have much meaning for hosts, roles and utilities but it is used in the
  topology controller. Each topology consists of one or more hosts and
  artifacts are collected from each host.
* ``artifacts_type`` identifies when artifacts are being collected. See its
  definition:

  .. literalinclude:: ../../../pytest_mh/_private/artifacts.py
      :caption: MultihostArtifactsType
      :start-after: +DOCS/MultihostArtifactsType
      :end-before: -DOCS/MultihostArtifactsType

Diagram
=======

.. mermaid::
    :align: center

    %%{init: {'theme': 'neutral'}}%%

    graph TD

        s --> host_pytest_setup --> host_pytest_setup_artifacts --> topology
        topology --> host_pytest_teardown -->host_pytest_teardown_artifacts --> e

        s(["`**Start**`"])
        e(["`**End**`"])

        host_pytest_setup("`**Setup hosts**
        MultihostHost.pytest_setup`")
        host_pytest_setup_artifacts("`**Collect hosts artifacts**
        type: pytest_setup`")

        host_pytest_teardown("`**Teardown hosts**
        MultihostHost.pytest_teardown`")

        host_pytest_teardown_artifacts("`**Collect hosts artifacts**
        type: pytest_teardown`")

        subgraph topology ["`**Topology**`"]
            topology_setup --> topology_setup_artifacts --> test
            test --> topology_teardown --> topology_teardown_artifacts

            topology_setup("`**Setup topology**
            TopologyController.topology_setup`")

            topology_setup_artifacts("`**Collect topology artifacts**
            type: topology_setup`")

            subgraph test ["`**Test run**`"]
                direction TB

                setup --> run(("`**Run test**`")) --> test_artifacts --> teardown

                setup("`**Setup before test**`")
                test_artifacts("`**Collect test artifacts**
                type: test`")
                teardown("`**Teardown after test**`")
            end

            topology_teardown("`**Teardown topology**
            TopologyController.topology_teardown`")

            topology_teardown_artifacts("`**Collect topology artifacts**
            type: topology_teardown`")
        end

    classDef section fill:#fff,stroke-width:2px,stroke:#ccc
    class topology,test section;

    classDef setup fill:#44d585,stroke-width:2px,stroke:#33d17a,font-size:1px
    class ue,hs,ts,rs,us setup;
    class uex,ht,tt,rt,ut setup;

    classDef artifacts fill:#ffbc00,stroke-width:0
    class host_pytest_setup_artifacts,host_pytest_teardown_artifacts,topology_setup_artifacts,topology_teardown_artifacts,test_artifacts artifacts;

    classDef test_node fill:#ff9,stroke-width:0
    class run test_node;
