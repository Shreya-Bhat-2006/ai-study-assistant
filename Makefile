.PHONY: build deploy test sync-layer

# Copy shared/ into the layer before building
sync-layer:
	cp -r shared/ layer/python/shared/

build: sync-layer
	sam build

deploy: build
	sam deploy

# Run tests locally (no AWS credentials needed — moto mocks everything)
test:
	pytest tests/ -v --tb=short
