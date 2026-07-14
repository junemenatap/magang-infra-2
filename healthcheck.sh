#!/bin/bash

time=$(date +%Y%m%d-%H%M%S)
outfile="healthcheck-$time.txt"
exec > "$outfile"

echo "===Health Check==="
echo "Hostname : $(hostname)"
echo "Waktu    : $(date)"
echo ""

echo "---Load Average---"
uptime
echo ""

echo "---Memory---"
free -h
echo ""

echo "---Disk---"
df -h
echo ""

echo "---IP---"
ip addr show | grep -E "inet " | awk '{print $2, $NF}'
echo ""

echo "---Ports---"
ss -tulpn
echo ""

echo "---SSH Service---"
systemctl is-active sshd
echo ""

echo "---Connectivity---"
if curl -s -o /dev/null -m 5 https://cloudflare.com; then
    echo "Internet connectivity: OK (cloudflare.com reachable)"
else
    echo "Internet connectivity: FAILED"
fi