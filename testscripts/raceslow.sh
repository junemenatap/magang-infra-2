#!/bin/bash

item=${1:-test}
pps=${2:-100}
mins=${3:-2}
ip=${4}
total=$((mins * 60))
end=$((SECONDS + total))

while [ $SECONDS -lt $end ]; do
    for ((i=1; i<=pps; i++)); do
        curl -s -X POST "http://$ip:8000/products/buy/${item}" > /dev/null &
    done
    wait
done

wait