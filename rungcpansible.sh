#!/bin/bash

ip=$1
vm_name=$2
vm_zone=$3

ssh-keygen -R $1

ssh-keygen -t rsa -b 4096 -f gcp/gcp_ssh_key -N ""

eval $(ssh-agent -s)

ssh-add ~/linux_training/hari5/gcp/gcp_ssh_key

gcloud compute instances add-metadata $2 \
  --metadata ssh-keys="june:$(cat ./gcp/gcp_ssh_key.pub)" \
  --zone $3

ssh june@$1

ansible-playbook -i ansible/inventories/gcp.ini ansible/deploy-beyla-demo.yml