# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

PULUMI ?= pulumi
VENV_DIR ?= .venv

# AUTO_APPROVE controls whether ``--yes`` is added to pulumi commands.  Set
# it to ``true`` or ``yes`` (case-sensitive) when running in CI or any
# non-interactive context; the default is ``false`` which leaves Pulumi in
# preview mode so you must manually confirm changes.
AUTO_APPROVE ?= false
# treat either "true" or "yes" (case-sensitive) as approval
APPROVE_FLAGS := $(if $(filter $(AUTO_APPROVE),true yes),--yes,)

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

.PHONY: install lint format test ci

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

test: ## Setup: Run tests
	@echo "$(GREEN)Running tests...$(NC)"
	@cd ec2-spot && \
	$(VENV_DIR)/bin/python -m pytest -q
	
ci: install lint format test ## Setup: Run CI checks (lint, format, test)
	@echo "$(GREEN)CI checks passed!$(NC)"

##@ Infra Commands

.PHONY: ec2-spot-preview ec2-spot-up ec2-spot-destroy ec2-spot-output

ec2-spot-preview: ## Infra: EC2 Spot Instance - Preview changes
	@echo "$(GREEN)Previewing EC2 Spot Instance deployment...$(NC)"
	@cd ec2-spot && $(PULUMI) preview

ec2-spot-up: ## Infra: EC2 Spot Instance - Deploy infrastructure
	@echo "$(GREEN)Deploying EC2 Spot Instance infrastructure...$(NC)"
	@cd ec2-spot && $(PULUMI) up $(APPROVE_FLAGS)

ec2-spot-destroy: ## Infra: EC2 Spot Instance - Destroy infrastructure
	@echo "$(GREEN)Destroying EC2 Spot Instance infrastructure...$(NC)"
	@cd ec2-spot && $(PULUMI) destroy $(APPROVE_FLAGS)

ec2-spot-output: ## Infra: EC2 Spot Instance - Show stack output
	@cd ec2-spot && \
	$(PULUMI) stack output