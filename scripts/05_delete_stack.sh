#!/usr/bin/env bash
set -euo pipefail
: "${AWS_REGION:=us-east-1}"
: "${STACK_NAME:=granescalaportfolio-app}"
aws cloudformation delete-stack --stack-name "${STACK_NAME}" --region "${AWS_REGION}"
echo "Delete started for stack ${STACK_NAME}."
