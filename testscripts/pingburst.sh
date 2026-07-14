#!/bin/bash

pps=${1:-500}
mins=${2:-2}
ip=${3}
total=$((mins * 60))
end=$((SECONDS + total))

while [ $SECONDS -lt $end ]; do
  for ((i=1; i<=pps; i++)); do curl -s http://$ip:8000/products > /dev/null & done
  sleep 30
done

wait