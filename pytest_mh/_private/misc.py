from __future__ import annotations

from copy import deepcopy
from functools import partial
from inspect import getfullargspec
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable

from .topology import Topology, TopologyDomain

if TYPE_CHECKING:
    from .multihost import MultihostConfig, MultihostDomain, MultihostHost


def merge_dict(*args: dict | None):
    """
    Merge two or more nested dictionaries together.

    Nested dictionaries are not overwritten but combined.
    """
    filtered_args = [x for x in args if x is not None]
    if not filtered_args:
        return {}

    dest = deepcopy(filtered_args[0])

    for source in filtered_args[1:]:
        for key, value in source.items():
            if isinstance(value, dict):
                dest[key] = merge_dict(dest.get(key, {}), value)
                continue

            dest[key] = value

    return dest


def invoke_callback(cb: Callable, /, **kwargs: Any) -> Any:
    """
    Invoke callback with given arguments.

    The callback may take all or only selected subset of given arguments.

    :param cb: Callback to call.
    :type cb: Callable
    :param `*kwargs`: Callback parameters.
    :type `*kwargs`: dict[str, Any]
    :param
    :return: Return value of the callabck.
    :rtype: Any
    """
    cb_args: list[str] = []

    # Get list of parameters required by the callback
    if isinstance(cb, partial):
        spec = getfullargspec(cb.func)

        cb_args = spec.args + spec.kwonlyargs

        # Remove bound positional parameters
        cb_args = cb_args[len(cb.args) :]

        # Remove bound keyword parameters
        cb_args = [x for x in cb_args if x not in cb.keywords]
    else:
        spec = getfullargspec(cb)
        cb_args = spec.args + spec.kwonlyargs

    if spec.varkw is None:
        # No **kwargs is present, just pick selected arguments
        callspec = {k: v for k, v in kwargs.items() if k in cb_args}
    else:
        # **kwargs is present, pass everything
        callspec = kwargs

    return cb(**callspec)


def topology_domain_to_host_namespace(
    topology_domain: TopologyDomain, mh_domain: MultihostDomain
) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]:
    """
    Convert topology domain into a namespace of MultihostHost objects accessible
    by roles names.

    :param topology_domain: Topology domain.
    :type topology_domain: TopologyDomain
    :param mh_domain: MultihostDomain
    :type mh_domain: MultihostDomain
    :return: Pair of namespace and path to host mapping.
    :rtype: tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]
    """
    ns = SimpleNamespace()
    paths: dict[str, MultihostHost | list[MultihostHost]] = {}

    for role_name in mh_domain.roles:
        if role_name not in topology_domain:
            continue

        count = topology_domain.get(role_name)
        hosts = [host for host in mh_domain.hosts_by_role(role_name)[:count]]
        setattr(ns, role_name, hosts)

        paths[f"{topology_domain.id}.{role_name}"] = hosts
        for index, host in enumerate(hosts):
            paths[f"{topology_domain.id}.{role_name}[{index}]"] = host

    return (ns, paths)


def topology_to_host_namespace(
    topology: Topology, mh_domains: list[MultihostDomain]
) -> tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]:
    """
    Convert topology into a namespace of MultihostHost objects accessible
    by domain id and roles names.

    :param topology: Topology.
    :type topology: Topology
    :param mh_domains: List of MultihostDomain
    :type mh_domains: list[MultihostDomain]
    :return: Pair of namespace and path to host mapping.
    :rtype: tuple[SimpleNamespace, dict[str, MultihostHost | list[MultihostHost]]]
    """
    root = SimpleNamespace()
    paths: dict[str, MultihostHost | list[MultihostHost]] = {}

    for mh_domain in mh_domains:
        if mh_domain.id in topology:
            ns, nspaths = topology_domain_to_host_namespace(topology.get(mh_domain.id), mh_domain)
            setattr(root, mh_domain.id, ns)
            paths.update(**nspaths)

    return root, paths


def topology_controller_parameters(
    mh_config: MultihostConfig, topology: Topology, fixtures: dict[str, str]
) -> dict[str, Any]:
    """
    Create dictionary of parameters for topology controller hooks.

    :param mh_config: MultihostConfig object.
    :type mh_config: MultihostConfig
    :param topology: Topology.
    :type topology: Topology
    :param fixtures: Topology fixtures.
    :type fixtures: dict[str, str]
    :return: Parameters.
    :rtype: dict[str, Any]
    """
    ns, paths = topology_to_host_namespace(topology, mh_config.domains)

    args = {}
    for name, path in fixtures.items():
        args[name] = paths[path]

    return {
        "mhc": mh_config,
        "logger": mh_config.logger,
        "ns": ns,
        **args,
    }
