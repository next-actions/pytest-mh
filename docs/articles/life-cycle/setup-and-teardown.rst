Setup and Teardown Hooks
########################

Pytest-mh provides multiple setup and teardown hooks that you can use to setup
the test environment and later revert all changes that were done during the
setup and testing.

It is possible to setup and teardown individual hosts, topologies, roles and
utilities. The scope of individual hooks spans from a whole pytest session
(called only once per session), topology (called once per multihost topology)
and test (called for each test).

.. contents::
    :local:

.. warning::

    Remember the golden rule: **everything that is done during setup must be
    reverted in teardown method for the same scope**. Every test should start
    with a fresh, untainted and clearly defined environment.

Scope: pytest session
=====================

These hooks are called only once and can be used for initial setup of the hosts
that is required for all tests. Setup is called once when pytest session starts,
then all collected tests are run and when then teardown is called right before
pytest session ends.

.. dropdown:: Setup
    :color: success
    :icon: gear
    :open:

    Setup is called on all hosts that are required to run collected test cases.

    #. Setup reentrant utilities used by the host. This is done automatically
       for all instances of :class:`~pytest_mh.MultihostReentrantUtility` that
       are available in the :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostUtility.setup`
       * :meth:`pytest_mh.MultihostReentrantUtility.__enter__`

    #. Setup host

       * :meth:`pytest_mh.MultihostHost.pytest_setup`

.. dropdown:: Run collected tests
    :color: primary
    :icon: iterations
    :open:

    Iterate over topologies and run tests. See: :ref:`setup_topology`.

.. dropdown:: Teardown
    :color: danger
    :icon: history
    :open:

    Teardown is called on all hosts that were required to run collected test cases.

    #. Teardown host

       * :meth:`pytest_mh.MultihostHost.pytest_teardown`

    #. Teardown reentrant utilities used by the host. This is done automatically
       for all instances of :class:`~pytest_mh.MultihostReentrantUtility` that
       are available in the :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__exit__`
       * :meth:`pytest_mh.MultihostUtility.teardown`

.. _setup_topology:

Scope: Multihost topology
=========================

The topology scope allows you to prepare hosts to run a specific topology. The
setup is run when a topology is entered the first time. After this step, all
tests for the currently selected topology are run and when these tests are
finished, then topology teardown is called.

.. dropdown:: Setup
    :color: success
    :icon: gear
    :open:

    #. Enter reentrant utilities used by the hosts required by this topology.
       This is done automatically for all instances of
       :class:`~pytest_mh.MultihostReentrantUtility` that are available in the
       :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__enter__`

    #. Setup topology

       * :meth:`pytest_mh.TopologyController.topology_setup`

.. dropdown:: Run collected tests
    :color: primary
    :icon: iterations
    :open:

    Run all tests that require current topology. See: :ref:`setup_test`.

.. dropdown:: Teardown
    :color: danger
    :icon: history
    :open:

    #. Teardown topology

       * :meth:`pytest_mh.TopologyController.topology_teardown`

    #. Exit reentrant utilities used by the hosts required by this topology.
       This is done automatically for all instances of
       :class:`~pytest_mh.MultihostReentrantUtility` that are available in the
       :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__exit__`

.. _setup_test:

Scope: Individual tests
=======================

These hooks are run once for each test.

.. dropdown:: Setup
    :color: success
    :icon: gear
    :open:

    #. Enter reentrant utilities used by the hosts required by the test.
       This is done automatically for all instances of
       :class:`~pytest_mh.MultihostReentrantUtility` that are available in the
       :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__enter__`

    #. Setup all hosts required by this test

       * :meth:`pytest_mh.MultihostHost.setup`

    #. Setup topology required by this test

       * :meth:`pytest_mh.TopologyController.setup`

    #. Setup utilities used by the roles. This is done automatically for all
       instances of :class:`~pytest_mh.MultihostUtility` that are available in
       the :class:`~pytest_mh.MultihostRole` object.

       * :meth:`pytest_mh.MultihostUtility.setup`
       * :meth:`pytest_mh.MultihostReentrantUtility.__enter__`

    #. Setup all roles required by this test

       * :meth:`pytest_mh.MultihostRole.setup`

.. dropdown:: Run test
    :color: primary
    :icon: iterations
    :open:

    Run the test.

.. dropdown:: Teardown
    :color: danger
    :icon: history
    :open:

    #. Teardown all roles required by this test

       * :meth:`pytest_mh.MultihostRole.teardown`

    #. Teardown utilities used by the roles. This is done automatically for all
       instances of :class:`~pytest_mh.MultihostUtility` that are available in
       the :class:`~pytest_mh.MultihostRole` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__exit__`
       * :meth:`pytest_mh.MultihostUtility.teardown`

    #. Teardown topology required by this test

       * :meth:`pytest_mh.TopologyController.teardown`

    #. Teardown all hosts required by this test

       * :meth:`pytest_mh.MultihostHost.teardown`

    #. Exit reentrant utilities used by the hosts required by the test.
       This is done automatically for all instances of
       :class:`~pytest_mh.MultihostReentrantUtility` that are available in the
       :class:`~pytest_mh.MultihostHost` object.

       * :meth:`pytest_mh.MultihostReentrantUtility.__exit__`

Diagram
=======

.. mermaid::
    :caption: Pytest-mh life cycle
    :align: center

    graph TD
        s([Start]) --> hps --> topology --> hca --> hpt --> e([End])

        hps("`**Setup hosts**
        MultihostHost.pytest_setup`")

        hca("`**Collect hosts artifacts**`")

        hpt("`**Teardown hosts**
        MultihostHost.pytest_teardown`")

        subgraph topology ["`**Topology**`"]
            tts --> test --> tta --> ttt

            tts("`**Setup topology**
            TopologyController.topology_setup`")

            tta("`**Collect topology artifacts**`")

            ttt("`**Teardown topology**
            TopologyController.topology_teardown`")

            subgraph test ["`**Test run**`"]
                direction TB

                ta("`**Collect test artifacts**`")

                subgraph setup ["`**Setup before test**`"]
                    direction LR
                    ue --> hs --> ts --> rs --> us

                    ue("`**Enter host utilities**
                    MultihostReentrantUtility.\_\_enter\_\_`")

                    hs("`**Setup hosts**
                    MultihostHost.setup`")

                    ts("`**Setup topology**
                    TopologyController.setup`")

                    rs("`**Setup roles**
                    MultihostRole.setup`")

                    us("`**Setup role utilities**
                    MultihostUtility.setup
                    MultihostReentrantUtility.\_\_enter\_\_`")
                end

                setup --> run(("`**Run test**`")) --> ta --> teardown

                subgraph teardown ["`**Teardown after test**`"]
                    direction LR
                    ut --> rt --> tt --> ht --> uex

                    uex("`**Exit host utilities**
                    MultihostReentrantUtility.\_\_exit\_\_`")

                    ht("`**Teardown hosts**
                    MultihostHost.teardown`")

                    tt("`**Teardown topology**
                    TopologyController.teardown`")

                    rt("`**Teardown roles**
                    MultihostRole.teardown`")

                    ut("`**Teardown role utilities**
                    MultihostUtility.teardown
                    MultihostReentrantUtility.\_\_exit\_\_`")
                end
            end
        end

    classDef section fill:#fff,stroke-width:2px,stroke:#ccc
    class topology,test section;

    classDef setup fill:#44d585,stroke-width:2px,stroke:#33d17a
    class ue,hs,ts,rs,us setup;
    class uex,ht,tt,rt,ut setup;

    classDef test_section fill:#eafaf1,stroke-width:0
    class setup,teardown test_section

    classDef test_node fill:#ff9,color:#ffffff,stroke-width:0
    class run,ta test_node;
