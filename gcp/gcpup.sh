#!/bin/bash

terraform init

sleep 10

terraform import google_compute_network.vpc_network projects/magang-it-aps/global/networks/magang-test

sleep 5

terraform plan

sleep 10

terraform apply --auto-approve
