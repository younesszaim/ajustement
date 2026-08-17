.PHONY: check test-backend test-frontend build-frontend generate-fields check-generated

PYTHON := .venv/bin/python

check: test-backend test-frontend build-frontend check-generated

test-backend:
	$(PYTHON) -m pytest backend/tests -q

test-frontend:
	npm --prefix frontend test -- --passWithNoTests

build-frontend:
	npm --prefix frontend run build

generate-fields:
	PYTHONPATH=backend $(PYTHON) backend/scripts/generate_frontend_fields.py

check-generated:
	@before=$$(git hash-object frontend/src/generated/fields.ts); \
	PYTHONPATH=backend $(PYTHON) backend/scripts/generate_frontend_fields.py; \
	after=$$(git hash-object frontend/src/generated/fields.ts); \
	test "$$before" = "$$after" || { \
		echo "Generated field metadata was stale; regenerated frontend/src/generated/fields.ts"; \
		exit 1; \
	}
