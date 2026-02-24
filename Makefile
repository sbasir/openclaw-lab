# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

AWS ?= aws
REGION ?= $(AWS_REGION)
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
	$(call print_help_section,Helpful Commands:,Helpful:)

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

.PHONY: ec2-spot-preview ec2-spot-up ec2-spot-destroy ec2-spot-output ec2-spot-deploy-logs

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

ec2-spot-deploy-logs: ## Infra: EC2 Spot Instance - Monitor bootstrap logs via SSM Session Manager
	@echo "📊 Monitoring bootstrap progress:"
	@cd ec2-spot && id=$$($(PULUMI) stack output instance_id 2>/dev/null); \
	if [ -z "$$id" ]; then echo "No instance_id in stack outputs. See 'make ec2-spot-output'"; exit 1; fi; \
	$(AWS) ssm start-session --target $$id --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo su -c \"tail -n 50 -f /var/log/cloud-init-output.log\""]' --region $(REGION)

##@ Helpful Commands

.PHONY: aws-describe-images openclaw-ec2-connect openclaw-gateway-session openclaw-dotenv-put-parameter

openclaw-ec2-connect: ## Helpful: Connect to EC2 Spot Instance via SSM Session Manager
	@cd ec2-spot && \
	id=$$($(PULUMI) stack output instance_id) && \
	if [ -z "$$id" ]; then echo "No instance_id in stack outputs. See 'make ec2-spot-output'"; exit 1; fi; \
	$(AWS) ssm start-session --target $$id --region $(REGION)

openclaw-gateway-session: ## Helpful: Connect to OpenClaw Gateway on EC2 Spot Instance via SSM Session Manager
	@cd ec2-spot && \
	id=$$($(PULUMI) stack output instance_id) && \
	if [ -z "$$id" ]; then echo "No instance_id in stack outputs. See 'make ec2-spot-output'"; exit 1; fi; \
	$(AWS) ssm start-session --target $$id --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["18789"], "localPortNumber":["18789"]}' --region $(REGION)

openclaw-dotenv-put-parameter: ## Helpful: Store .env contents securely in AWS SSM Parameter Store
	@$(AWS) ssm put-parameter --name "/openclaw-lab/dotenv" --value "$$(cat .env)" --type "SecureString" --overwrite --region $(REGION)

aws-describe-images: ## Helpful: List available Amazon Linux 2023 AMIs
	@$(AWS) ec2 describe-images --owners amazon \
	  --filters "Name=name,Values=al2023-ami-2023*-arm64" \
	  --query 'Images[?contains(Name, `ecs`)==`false`].[CreationDate,Name,ImageId]' --output text | sort