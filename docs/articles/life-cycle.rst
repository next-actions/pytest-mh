Life Cycle and Hooks
####################

One of the most fundamental features of pytest-mh is to provide users a way to
setup hosts before a test is run, collect test artifacts and revert all changes
that were done during the test afterwards. Therefore it provides multiple hooks
that will execute your code in order to achieve smooth and extensive setup and
teardown and more.

.. toctree::
    :maxdepth: 2

    life-cycle/artifacts-collection
    life-cycle/setup-and-teardown
    life-cycle/skipping-tests
    life-cycle/changing-test-status


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
