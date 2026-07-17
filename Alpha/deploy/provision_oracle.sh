#!/usr/bin/env bash
# Alpha Oracle 一键建机(在 owner 的 Cloud Shell 里运行:已用委派令牌认证,无需密钥)
# 用法: curl -sL https://raw.githubusercontent.com/LinzeColin/MetaDatabase/main/Alpha/deploy/provision_oracle.sh | bash
# 幂等:VCN/子网存在则复用;A1 免费容量缺货自动跨 AD 重试。零成本(Always Free)。
set -euo pipefail
C="${OCI_TENANCY:?需在 Oracle Cloud Shell 运行(OCI_TENANCY 未设)}"
PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDkCq8P6VZo3puuv2ezZfcaAvK07b/pKtVWg6McpC28S alpha-oracle-deploy"
NAME="alpha-prod"

echo ">> 1/5 复用已运行的 alpha-prod?"
EXIST=$(oci compute instance list -c "$C" --display-name "$NAME" --lifecycle-state RUNNING --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -n "$EXIST" ] && [ "$EXIST" != "null" ]; then
  IP=$(oci compute instance list-vnics --instance-id "$EXIST" --query 'data[0]."public-ip"' --raw-output)
  echo "ALPHA_ALREADY_RUNNING instance=$EXIST public_ip=$IP"; exit 0
fi

echo ">> 2/5 Ubuntu 22.04 (aarch64) 镜像"
IMG=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" \
  --operating-system-version "22.04" --shape "VM.Standard.A1.Flex" \
  --sort-by TIMECREATED --query 'data[0].id' --raw-output)
[ -n "$IMG" ] && [ "$IMG" != "null" ] || { echo "FAIL: 未找到 Ubuntu 22.04 A1 镜像"; exit 1; }

echo ">> 3/5 网络(复用或新建 alpha-vcn + 公有子网)"
VCN=$(oci network vcn list -c "$C" --display-name alpha-vcn --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -z "$VCN" ] || [ "$VCN" = "null" ]; then
  VCN=$(oci network vcn create -c "$C" --display-name alpha-vcn --cidr-blocks '["10.0.0.0/16"]' \
    --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true \
    --display-name alpha-igw --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
  oci network route-table update --rt-id "$RT" --force \
    --route-rules '[{"destination":"0.0.0.0/0","networkEntityId":"'"$IGW"'"}]' >/dev/null
  SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
  oci network security-list update --security-list-id "$SL" --force \
    --ingress-security-rules '[{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":443,"max":443}}}]' \
    --egress-security-rules '[{"protocol":"all","destination":"0.0.0.0/0"}]' >/dev/null
  SUBNET=$(oci network subnet create -c "$C" --vcn-id "$VCN" --display-name alpha-subnet \
    --cidr-block 10.0.0.0/24 --wait-for-state AVAILABLE --query 'data.id' --raw-output)
else
  SUBNET=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output)
fi

echo ">> 4/5 拉取 cloud-init 并组装启动元数据"
curl -sfL https://raw.githubusercontent.com/LinzeColin/MetaDatabase/main/Alpha/deploy/cloud-init.yaml -o /tmp/alpha-cloud-init.yaml
UD=$(base64 -w0 /tmp/alpha-cloud-init.yaml)
printf '{"ssh_authorized_keys":"%s","user_data":"%s"}' "$PUBKEY" "$UD" > /tmp/alpha-meta.json

echo ">> 5/5 启动 A1.Flex 2核12G(容量缺货则跨 AD 重试)"
mapfile -t ADS < <(oci iam availability-domain list --query 'data[].name' --raw-output | tr -d '[],"' | sed '/^$/d')
IID=""
for attempt in 1 2 3; do
  for AD in "${ADS[@]}"; do
    AD=$(echo "$AD" | xargs)
    [ -n "$AD" ] || continue
    echo "   尝试 AD=$AD (第 $attempt 轮)"
    if oci compute instance launch -c "$C" --availability-domain "$AD" \
        --shape VM.Standard.A1.Flex --shape-config '{"ocpus":2,"memoryInGBs":12}' \
        --image-id "$IMG" --subnet-id "$SUBNET" --assign-public-ip true \
        --display-name "$NAME" --metadata "file:///tmp/alpha-meta.json" \
        --wait-for-state RUNNING --query 'data.id' --raw-output > /tmp/alpha-iid 2>/tmp/alpha-err; then
      IID=$(cat /tmp/alpha-iid); break
    fi
    if grep -qi "Out of host capacity\|LimitExceeded" /tmp/alpha-err; then
      echo "   该 AD 暂无 A1 免费容量,换下一个"; continue
    fi
    echo "FAIL 启动报错:"; cat /tmp/alpha-err; exit 1
  done
  [ -n "$IID" ] && break
  echo "   全部 AD 暂无容量,60s 后重试..."; sleep 60
done
[ -n "$IID" ] || { echo "ALPHA_NO_CAPACITY: 悉尼区 A1 免费容量暂时售罄,稍后重跑本脚本即可(常在数小时内释放)"; exit 2; }

IP=$(oci compute instance list-vnics --instance-id "$IID" --query 'data[0]."public-ip"' --raw-output)
echo ""
echo "ALPHA_PROVISIONED instance=$IID public_ip=$IP"
echo ">> 云主机已 RUNNING,cloud-init 正在后台加固+装五进程。SSH:ssh -i ~/.ssh/alpha_oracle_ed25519 ubuntu@$IP"
