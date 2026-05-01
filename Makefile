.PHONY: help install run test test-unit test-integration test-cov lint format up down setup-local-aws

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	pip install -e ".[dev]"

run: ## Start the FastAPI server (hot-reload)
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v

test-cov: ## Run tests with coverage report (minimum 80%)
	pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80

lint: ## Lint with ruff
	ruff check src/ tests/

format: ## Format code with ruff
	ruff format src/ tests/

up: ## Start Docker Compose (API + LocalStack)
	docker compose -f infrastructure/docker-compose.yml up -d

down: ## Stop Docker Compose
	docker compose -f infrastructure/docker-compose.yml down

setup-local-aws: ## Create S3 bucket + DynamoDB table in LocalStack
	@echo "Waiting for LocalStack..."
	@sleep 3
	awslocal s3 mb s3://contract-analyzer-docs --region us-east-1 || true
	awslocal dynamodb create-table \
		--table-name contract-analyzer-runs \
		--attribute-definitions AttributeName=run_id,AttributeType=S \
		--key-schema AttributeName=run_id,KeyType=HASH \
		--billing-mode PAY_PER_REQUEST \
		--region us-east-1 || true
	@echo "AWS resources created."

sample-request: ## Send a sample PDF to the running API
	curl -X POST http://localhost:8000/analyze \
		-F "file=@tests/fixtures/sample_contracts/sample_contract.pdf" \
		-H "Accept: text/event-stream" \
		--no-buffer

clean: ## Remove Python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
