import pytest

from network_helpers import (
    allocate_ipv4_subnets,
    allocate_ipv6_subnets,
    allocate_ipv6_subnets_from_optional,
    canonicalize_ipv4_cidr,
    ipv4_subnets_cidrs,
)

# NOTE: allocate_ipv6_subnet_output_for_azs and ipv6_subnets_cidrs wrap
# pulumi.Output and require a running Pulumi runtime to test. Their underlying
# logic is fully covered by the allocate_ipv6_subnets* tests below.


class TestCanonicalize:
    def test_normalizes_host_bits_to_network_address(self) -> None:
        # AWS CreateVpc/CreateSubnet silently canonicalize host bits.
        assert canonicalize_ipv4_cidr("10.0.77.19/16") == "10.0.0.0/16"

    def test_already_canonical_cidr_is_unchanged(self) -> None:
        assert canonicalize_ipv4_cidr("10.0.0.0/16") == "10.0.0.0/16"

    def test_normalizes_32_host_prefix(self) -> None:
        assert canonicalize_ipv4_cidr("10.0.0.1/32") == "10.0.0.1/32"


class TestAllocateIPv4Subnets:
    def test_allocates_sequential_from_16(self) -> None:
        result = allocate_ipv4_subnets("10.0.0.0/16", 3, subnet_prefix=24)
        assert result == ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]

    def test_normalizes_non_network_base_before_allocation(self) -> None:
        # strict=False normalizes 10.0.77.19/16 to its containing network
        # 10.0.0.0/16; subnets start from the beginning of that network.
        result = allocate_ipv4_subnets("10.0.77.19/16", 2, subnet_prefix=24)
        assert result == ["10.0.0.0/24", "10.0.1.0/24"]

    def test_normalizes_host_bits_for_same_prefix(self) -> None:
        result = allocate_ipv4_subnets("10.0.77.19/24", 1, subnet_prefix=24)
        assert result == ["10.0.77.0/24"]

    def test_returns_exact_count_not_all_subnets(self) -> None:
        result = allocate_ipv4_subnets("10.0.0.0/16", 2, subnet_prefix=24)
        assert len(result) == 2

    def test_raises_when_not_enough_space(self) -> None:
        # A /24 base has exactly one /24 subnet, so requesting 2 must fail.
        with pytest.raises(ValueError, match="Not enough /24 subnets"):
            allocate_ipv4_subnets("10.0.0.0/24", 2, subnet_prefix=24)

    def test_raises_when_subnet_prefix_smaller_than_base(self) -> None:
        with pytest.raises(ValueError, match="must be at least base prefix"):
            allocate_ipv4_subnets("10.0.0.0/16", 1, subnet_prefix=15)

    def test_raises_for_ipv6_input(self) -> None:
        with pytest.raises(ValueError, match="Expected an IPv4 CIDR block"):
            allocate_ipv4_subnets("2600:1f14:abcd::/56", 2, subnet_prefix=24)


class TestIPv4SubnetsCidrs:
    """ipv4_subnets_cidrs is the AZ-facing wrapper: always /24, count == az_count."""

    def test_returns_one_24_per_az(self) -> None:
        result = ipv4_subnets_cidrs("10.0.0.0/16", az_count=3)
        assert result == ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]

    def test_single_az(self) -> None:
        result = ipv4_subnets_cidrs("172.16.0.0/16", az_count=1)
        assert result == ["172.16.0.0/24"]

    def test_raises_when_base_too_small_for_az_count(self) -> None:
        with pytest.raises(ValueError, match="Not enough /24 subnets"):
            ipv4_subnets_cidrs("10.0.0.0/24", az_count=2)


class TestAllocateIPv6Subnets:
    def test_allocates_sequential_from_56(self) -> None:
        result = allocate_ipv6_subnets("2600:1f14:abcd:1200::/56", 3, subnet_prefix=64)
        assert result == [
            "2600:1f14:abcd:1200::/64",
            "2600:1f14:abcd:1201::/64",
            "2600:1f14:abcd:1202::/64",
        ]

    def test_returns_exact_count_not_all_subnets(self) -> None:
        result = allocate_ipv6_subnets("2600:1f14:abcd:1200::/56", 1, subnet_prefix=64)
        assert len(result) == 1

    def test_raises_when_not_enough_space(self) -> None:
        with pytest.raises(ValueError, match="Not enough /64 subnets"):
            allocate_ipv6_subnets("2600:1f14:abcd:1200::/64", 2, subnet_prefix=64)

    def test_raises_for_ipv4_input(self) -> None:
        with pytest.raises(ValueError, match="Expected an IPv6 CIDR block"):
            allocate_ipv6_subnets("10.0.0.0/16", 2, subnet_prefix=64)


class TestAllocateIPv6SubnetsFromOptional:
    """Handles cases where the VPC IPv6 CIDR may not be available yet."""

    def test_returns_empty_list_for_none(self) -> None:
        assert allocate_ipv6_subnets_from_optional(None, 3) == []

    def test_returns_empty_list_for_empty_string(self) -> None:
        assert allocate_ipv6_subnets_from_optional("", 3) == []

    def test_allocates_when_cidr_present(self) -> None:
        result = allocate_ipv6_subnets_from_optional("2600:1f14:abcd:1200::/56", 2)
        assert result == ["2600:1f14:abcd:1200::/64", "2600:1f14:abcd:1201::/64"]

    def test_defaults_to_64_prefix(self) -> None:
        result = allocate_ipv6_subnets_from_optional("2600:1f14:abcd:1200::/56", 1)
        assert result == ["2600:1f14:abcd:1200::/64"]
