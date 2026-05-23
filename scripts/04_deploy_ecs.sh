#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${STACK_NAME:=granescalaportfolio-app}"
: "${SERVICE_NAME:=granescalaportfolio}"
: "${ATHENA_DATABASE:=portfolio_db}"
: "${BEDROCK_MODEL_ID:=us.anthropic.claude-sonnet-4-6}"
: "${IMAGE_URI:?Set IMAGE_URI first, for example export IMAGE_URI=...}"
: "${BUCKET:?Set BUCKET first}"

ATHENA_OUTPUT_S3="s3://${BUCKET}/athena-results/"

VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" \
  --output text \
  --region "${AWS_REGION}")

SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=defaultForAz,Values=true" \
  --query "Subnets[*].SubnetId" \
  --output text \
  --region "${AWS_REGION}" | tr '\t' ',')

aws cloudformation deploy \
  --template-file infrastructure/ecs-fargate-streamlit.yaml \
  --stack-name "${STACK_NAME}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId="${VPC_ID}" \
    SubnetIds="${SUBNET_IDS}" \
    ImageUri="${IMAGE_URI}" \
    ServiceName="${SERVICE_NAME}" \
    AthenaDatabase="${ATHENA_DATABASE}" \
    AthenaOutputS3="${ATHENA_OUTPUT_S3}" \
    BedrockModelId="${BEDROCK_MODEL_ID}" \
  --region "${AWS_REGION}"

aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --region "${AWS_REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='AppURL'].OutputValue" \
  --output text
