#!/bin/bash

end=$((SECONDS+120))
while [ $SECONDS -lt $end ]; do
  for i in {1..30}; do
    curl -s http://localhost:8000/products > /dev/null &
    curl -s -X POST "http://localhost:8000/products?name=test$RANDOM&price=10" > /dev/null &
  done
  wait
done
