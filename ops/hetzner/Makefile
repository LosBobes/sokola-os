# Shorthand for the SOKOLA Hetzner deploy.
#
# Set HETZNER_HOST / HETZNER_USER in your shell profile (same names as the
# GitHub Actions secrets) or pass them on the command line:
#   export HETZNER_HOST=1.2.3.4   HETZNER_USER=root
#   make -f ops/hetzner/Makefile ssh HETZNER_HOST=1.2.3.4 HETZNER_USER=root
HETZNER_USER ?= root
HOST         ?= $(HETZNER_USER)@$(HETZNER_HOST)
DEPLOY_PATH  ?= /opt/sokola

.PHONY: ssh logs deploy

# SSH into the server.
ssh:
	ssh $(HOST)

# Tail the running container logs.
logs:
	ssh $(HOST) "cd $(DEPLOY_PATH) && docker compose -f compose.prod.yml --env-file ops/hetzner/.env logs -f"

# Manual deploy (the GitHub Action does this automatically on push to main).
deploy:
	ssh $(HOST) "cd $(DEPLOY_PATH) && git fetch origin main && git reset --hard origin/main && docker compose -f compose.prod.yml --env-file ops/hetzner/.env up --build -d --remove-orphans && docker image prune -f"
