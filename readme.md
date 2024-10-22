> [!WARNING]
> This plugin is still actively developed and even though it is mostly stable,
> we reserve the right to introduce minor breaking changes if it is required for
> new functionality. Therefore we advise to pin `pytest-mh` version for your
> project.

# pytest_mh - pytest multihost test framework

`pytest-mh` is a pytest plugin that, at a basic level, allows you to run shell
commands and scripts over SSH on remote Linux or Windows hosts. You use it to
execute system or application tests for your project on a remote host or hosts
(or containers) while running pytest locally keeping your local machine intact.

The plugin also provides building blocks that can be used to setup and teardown
your tests, perform automatic clean up of all changes done on the remote host,
and build a flexible and unified high-level API to manipulate the hosts from
your tests.

## Documentation

**See the full documentation here: https://pytest-mh.readthedocs.io.**

## Example usage

The following snippet was taken from the [SSSD](https://github.com/SSSD/sssd)
project.

```python
    @pytest.mark.topology(KnownTopology.AD)
    @pytest.mark.topology(KnownTopology.LDAP)
    @pytest.mark.topology(KnownTopology.IPA)
    @pytest.mark.topology(KnownTopology.Samba)
    def test__id(client: Client, provider: GenericProvider):
        u = provider.user("tuser").add()
        provider.group("tgroup_1").add().add_member(u)
        provider.group("tgroup_2").add().add_member(u)

        client.sssd.start()
        result = client.tools.id("tuser")

        assert result is not None
        assert result.user.name == "tuser"
        assert result.memberof(["tgroup_1", "tgroup_2"])
```