# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

PULUMI ?= pulumi
VENV_DIR ?= .venv

define print_help_section
	@echo "$(YELLOW)$(1)$(NC)"
	@grep -E '^[a-zA-Z0-9_-]+:.*##[!]? .*$$' $(MAKEFILE_LIST) | \
	grep "$(2)" | \
	awk -F '##' \
	'{ \
	    cmd=$$1; \
	    gsub(/:.*/,"",cmd); \
	    desc=$$NF; \
	    gsub(/^[!]? /,"",desc); \
	    marker = ($$0 ~ /##!/) ? "⭐" : "  "; \
		printf "  $(GREEN)%-30s$(NC)  %s  %s\n", cmd, marker, desc \
	}'
	@echo ""
endef


.PHONY: help

help: ## Show this help message
	@echo "$(GREEN)OpenClaw Lab - Commands$(NC)"
	@echo ""
	$(call print_help_section,Setup Commands:,Setup:)
	$(call print_help_section,Infrastructure Commands:,Infra:)

##@ Setup Commands

.PHONY: install lint format

install: ## Setup: Install all dependencies
	@echo "$(GREEN)Installing dependencies...$(NC)"
	@cd ec2-spot && $(PULUMI) install

lint: ## Setup: Lint the code
	@echo "$(GREEN)Linting the code...$(NC)"
	@cd ec2-spot && \
	$(VENV_DIR)/bin/ruff check .

format: ## Setup: Format the code
	@echo "$(GREEN)Formatting the code...$(NC)"
	@cd ec2-spot && \
	$(VENV_DIR)/bin/ruff format .

##@ Infra Commands

.PHONY: ec2-spot-preview ec2-spot-up ec2-spot-destroy ec2-spot-output

ec2-spot-preview: ## Infra: EC2 Spot Instance - Preview changes
	@echo "$(GREEN)Previewing EC2 Spot Instance deployment...$(NC)"
	@cd ec2-spot && $(PULUMI) preview

ec2-spot-up: ## Infra: EC2 Spot Instance - Deploy infrastructure
	@echo "$(GREEN)Deploying EC2 Spot Instance infrastructure...$(NC)"
	@cd ec2-spot && $(PULUMI) up --yes

ec2-spot-destroy: ## Infra: EC2 Spot Instance - Destroy infrastructure
	@echo "$(GREEN)Destroying EC2 Spot Instance infrastructure...$(NC)"
	@cd ec2-spot && $(PULUMI) destroy

ec2-spot-output: ## Infra: EC2 Spot Instance - Show stack output
	@cd ec2-spot && \
	$(PULUMI) stack output