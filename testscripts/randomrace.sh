#!/bin/bash

pps=${1:-100}
mins=${2:-2}
ip=${3}
total=$((mins * 60))
end=$((SECONDS + total))

my_list=("test" "try" "tests")

while [ $SECONDS -lt $end ]; do
    for ((i=1; i<=pps; i++)); do
        item=${my_list[$RANDOM % ${#my_list[@]}]}
        curl -s -X POST "http://$ip:8000/products/buy/${item}" > /dev/null &
    done
    wait
done

wait