"""Utility helpers for VPC subnet CIDR calculations.

This module contains pure-Python routines that compute (and in the case of
IPv6, wrap Pulumi outputs for) the subnets needed when creating a VPC with one
subnet per availability zone.  The functions are intentionally kept free of
Pulumi imports so they can be tested and exercised without a Pulumi runtime.

The IPv4 helpers also automatically canonicalize CIDR blocks using
``ipaddress.ip_network(..., strict=False)``.  AWS behaves the same way when you
call ``CreateVpc``/``CreateSubnet``: any host bits provided in the configuration
are silently zeroed rather than raising an error.  ``canonicalize_ipv4_cidr``
exists to mirror that behaviour and keep configuration logic consistent.
"""

import ipaddress
from typing import Any, Optional


def canonicalize_ipv4_cidr(cidr: str) -> str:
    # Intentionally mirrors AWS CreateVpc/CreateSubnet behavior, which canonicalizes
    # host bits in CIDR input instead of rejecting it.
    return str(ipaddress.ip_network(cidr, strict=False))


def allocate_ipv4_subnets(
    base_cidr: str, subnet_count: int, subnet_prefix: int = 24
) -> list[str]:
    # strict=False mirrors AWS CIDR canonicalization semantics.
    network = ipaddress.ip_network(base_cidr, strict=False)
    if network.version != 4:
        raise ValueError(f"Expected an IPv4 CIDR block, got: {base_cidr}")
    if subnet_prefix < network.prefixlen:
        raise ValueError(
            f"Subnet prefix /{subnet_prefix} must be at least base prefix /{network.prefixlen}"
        )

    subnets = [str(subnet) for subnet in network.subnets(new_prefix=subnet_prefix)]
    if len(subnets) < subnet_count:
        raise ValueError(
            f"Not enough /{subnet_prefix} subnets in {base_cidr} for {subnet_count} availability zones"
        )
    return subnets[:subnet_count]


def allocate_ipv6_subnets(
    base_cidr: str, subnet_count: int, subnet_prefix: int = 64
) -> list[str]:
    # strict=False mirrors AWS CIDR canonicalization semantics.
    network = ipaddress.ip_network(base_cidr, strict=False)
    if network.version != 6:
        raise ValueError(f"Expected an IPv6 CIDR block, got: {base_cidr}")
    if subnet_prefix < network.prefixlen:
        raise ValueError(
            f"Subnet prefix /{subnet_prefix} must be at least base prefix /{network.prefixlen}"
        )

    subnets = [str(subnet) for subnet in network.subnets(new_prefix=subnet_prefix)]
    if len(subnets) < subnet_count:
        raise ValueError(
            f"Not enough /{subnet_prefix} subnets in {base_cidr} for {subnet_count} availability zones"
        )
    return subnets[:subnet_count]


def ipv4_subnets_cidrs(base_cidr: str, az_count: int) -> list[str]:
    return allocate_ipv4_subnets(base_cidr, az_count, subnet_prefix=24)


def allocate_ipv6_subnets_from_optional(
    base_cidr: Optional[str], subnet_count: int, subnet_prefix: int = 64
) -> list[str]:
    if not base_cidr:
        return []
    return allocate_ipv6_subnets(base_cidr, subnet_count, subnet_prefix=subnet_prefix)


def allocate_ipv6_subnet_output_for_azs(base_cidr_output: Any, az_count: int) -> Any:
    return base_cidr_output.apply(
        lambda cidr: allocate_ipv6_subnets_from_optional(
            cidr, az_count, subnet_prefix=64
        )
    )


def ipv6_subnets_cidrs(base_cidr_output: Any, az_count: int) -> list[Any]:
    """Pre-expand VPC IPv6 CIDR into one Output[str] per AZ, avoiding index
    access inside resource-creation loops."""
    all_cidrs = allocate_ipv6_subnet_output_for_azs(base_cidr_output, az_count)
    return [all_cidrs.apply(lambda cidrs, i=idx: cidrs[i]) for idx in range(az_count)]
