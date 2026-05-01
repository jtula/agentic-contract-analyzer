#!/bin/bash
# LocalStack init script — creates AWS resources on container startup.
# Runs automatically when LocalStack reaches the "ready" state.

echo "==> Creating S3 bucket..."
awslocal s3 mb s3://contract-analyzer-docs

echo "==> Creating DynamoDB table..."
awslocal dynamodb create-table \
  --table-name contract-analyzer-runs \
  --attribute-definitions AttributeName=run_id,AttributeType=S \
  --key-schema AttributeName=run_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

echo "==> LocalStack resources ready."
