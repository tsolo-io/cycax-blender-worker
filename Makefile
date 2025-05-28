# SPDX-FileCopyrightText: 2025 Tsolo.io
#
# SPDX-License-Identifier: Apache-2.0

.ONESHELL: # Run all the commands in the same shell
.PHONY: docs
.DEFAULT_GOAL := help
TAG := $(shell hatch version)

all: help

help:
	@echo "Help"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build: ## Build containers
	hatch dep show requirements > requirements.txt
	hatch build
	docker build -t "tsolo/cycax-blender-worker:${shell hatch version}" .
	# docker compose build

run: ## Run the CyCAx Server directly
	hatch run python3.11 ./src/cycax_blender_worker/main.py

test: ## Run the basic unit tests, skip the ones that require a connection to ceph cluster.
	hatch run testing:test

test-on-ci: ## Run all the unit tests with code coverage and reporting, for Jenkins
	mkdir -p reports/coverage
	hatch run testing:cov

format: ## Format the source code
	hatch run lint:fmt

spelling:
	hatch run lint:spell

docs:
	hatch run docs:build

docs-open: ## Open the documentation in your default browser (Linux only)
	open docs/site/index.html

docs-serve: ## Run the documentation server locally
	hatch run docs:serve

start: ## Start the development environment with docker compose
	CURRENT_UID=$(shell id -u):$(shell id -g) docker compose up -d

stop: ## Stop the docker compose development environment
	CURRENT_UID=$(shell id -u):$(shell id -g) docker compose down

ps: ## Show the docker compose development environment processes
	CURRENT_UID=$(shell id -u):$(shell id -g) docker compose ps

logs: ## Show the docker compose development environment logs
	docker compose logs -f

restart: stop start ## Restart the docker compose development environment

