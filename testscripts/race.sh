#!/bin/bash

item=${1:-test}
pps=${2:-100}
ip=${3}

for ((i=1; i<=pps; i++)); do
    curl -s -X POST "http://$ip:8000/products/buy/${item}" > /dev/null &
done
wait