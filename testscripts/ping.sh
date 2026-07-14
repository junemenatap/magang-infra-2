#!/bin/bash

pps=${1:-50}
mins=${2:-2}
ip=${3}
total=$((mins * 60))
end=$((SECONDS + total))

while [ $SECONDS -lt $end ]; do
  for ((i=1; i<=pps; i++)); do curl -s http://$ip:8000/order > /dev/null & done
  sleep 1
done

wait
