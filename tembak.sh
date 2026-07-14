#!/bin/bash

for i in {1..150}; do
  curl -s http://34.48.27.251:8000/order > /dev/null
  sleep 0.5
done
