#!/bin/bash

terraform init

sleep 10

terraform plan

sleep 10

terraform apply --auto-approve
