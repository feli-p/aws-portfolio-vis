#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${ECR_REPO:=granescalaportfolio-streamlit}"
: "${IMAGE_TAG:=$(date +%Y%m%d%H%M%S)}"

unset AWS_PROFILE || true
unset AWS_ACCESS_KEY_ID || true
unset AWS_SECRET_ACCESS_KEY || true
unset AWS_SESSION_TOKEN || true

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}" >/dev/null 2>&1 || true

aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build --network sagemaker -t "${ECR_REPO}:${IMAGE_TAG}" -t "${ECR_REPO}:latest" .
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:latest"

echo "IMAGE_URI=${ECR_URI}:${IMAGE_TAG}"
echo "LATEST_URI=${ECR_URI}:latest"
