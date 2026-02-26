#!/bin/bash
set -euo pipefail

REGION=""
INSTANCE_TYPES=""

usage() {
    cat >&2 <<EOF
Usage: $(basename "$0") --region REGION --instance-types INSTANCE_TYPES

Examples:
  $(basename "$0") --region us-east-1 --instance-types "t4g.small t4g.medium"
  $(basename "$0") --region eu-west-1 --instance-types "t3.micro"
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --region)
            REGION="$2"
            shift 2
            ;;
        --instance-types)
            INSTANCE_TYPES="$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo "Error: Unknown option '$1'" >&2
            usage
            ;;
    esac
done

if [[ -z "$REGION" ]] || [[ -z "$INSTANCE_TYPES" ]]; then
    cat >&2 <<EOF
Error: Required arguments missing. 
Usage via script:   $(basename "$0") --region <region> --instance-types "<types>"
Usage via Makefile: make ec2-spot-prices [REGION=<region>] [INSTANCE_TYPES="<types>"]
EOF
    exit 1
fi

echo "Region: $REGION (Spot prices, sorted by price, unique AZ+InstanceType)"

tmp_specs=$(mktemp)
trap "rm -f '$tmp_specs'" EXIT

# Fetch instance type specifications using provided AWS command or default to aws
AWS_CMD="${AWS:-aws}"

$AWS_CMD ec2 describe-instance-types \
    --instance-types $INSTANCE_TYPES \
    --region "$REGION" \
    --output json | \
jq -r '.InstanceTypes[] | [.InstanceType, .VCpuInfo.DefaultVCpus, .MemoryInfo.SizeInMiB] | @tsv' > "$tmp_specs"

# Fetch and process spot prices
$AWS_CMD ec2 describe-spot-price-history \
    --region "$REGION" \
    --instance-types $INSTANCE_TYPES \
    --product-descriptions "Linux/UNIX" \
    --max-items 500 \
    --no-cli-pager \
    --output json | \
jq -r '.SpotPriceHistory | unique_by(.InstanceType + ":" + .AvailabilityZone) | sort_by(.SpotPrice | tonumber) | .[] | [.AvailabilityZone, .InstanceType, (.SpotPrice | tonumber)] | @tsv' | \
awk -v specs="$tmp_specs" '
BEGIN {
    OFS = "\t"
    while ((getline < specs) > 0) {
        specmap[$1] = $2 "\t" $3
    }
    close(specs)
    print "AZ", "InstanceType", "VCpus", "MemoryMiB", "PriceUSD/hr", "PriceUSD/mo"
}
{
    vcpus_mem = specmap[$2]
    split(vcpus_mem, vm, "\t")
    printf "%s\t%s\t%s\t%s\t%.6f\t%.2f\n", $1, $2, vm[1], vm[2], $3, $3 * 730
}
' | column -t