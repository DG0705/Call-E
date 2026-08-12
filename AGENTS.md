# Call-E Coding Agent Instructions

## Project Vision

Call-E is an enterprise AI workforce platform designed to replace traditional call-center/BPO workflows with autonomous, human-like AI voice agents that can understand customers and complete real business tasks.

Call-E is not an IVR system or a simple scripted voice bot.

## Current Architecture

- Language: Python 3.13
- Backend: FastAPI
- Architecture: Microservices
- Database: MongoDB
- Message broker: RabbitMQ
- API gateway / reverse proxy: Traefik
- Containerization: Docker / Docker Compose
- Python dependency management: uv
- Version control: Git / GitHub

## Core Architectural Decisions

- Keep services independently deployable.
- Keep business logic inside the appropriate service, not in shared utilities or API routes.
- Reuse the shared runtime for configuration, logging, request IDs, health handling, and common response contracts.
- Use asynchronous FastAPI patterns where appropriate.
- Keep database access behind repository/service abstractions.
- Keep API routes thin: validate input, call application/service logic, return the API contract.
- Use RabbitMQ for asynchronous inter-service events where appropriate.
- Use REST APIs for synchronous service communication.
- MongoDB is the source of persistence for platform domain data.

## AI Architecture Principle

The AI reasons and plans; tools execute real-world actions.

Do not allow an LLM to directly perform external side effects. External actions such as CRM updates, ticket creation, booking, refunds, emails, or other mutations must go through explicit tools/services with validation and authorization.

## Coding Rules

- Inspect the existing repository before changing architecture or introducing new abstractions.
- Preserve existing conventions unless there is a clear technical reason to change them.
- Prefer simple, maintainable implementations over premature abstractions.
- Do not create a new microservice for a small feature unless the domain boundary genuinely requires it.
- Do not duplicate functionality already provided by the shared package.
- Keep type hints on public functions and important internal interfaces.
- Use Ruff-compatible formatting and linting.
- Use pytest for tests.
- Keep tests focused and fast.
- Never commit secrets, credentials, API keys, tokens, or private configuration.
- Use environment variables for configuration and provide safe defaults only where appropriate for local development.

## API Rules

- Version public APIs under `/api/v1/`.
- Keep response schemas stable and typed.
- Preserve request ID propagation.
- Use the shared response utilities where applicable.
- Do not put business logic directly inside route handlers.

## Database Rules

- Keep MongoDB access isolated from route handlers.
- Do not create ad-hoc database access code across multiple modules.
- Add indexes deliberately when introducing query-heavy collections.
- Store timestamps consistently.
- Keep tenant isolation in mind for every business-domain collection.

## Multi-Tenancy

Call-E is intended to serve multiple organizations. Domain data should be designed with tenant isolation in mind.

Do not introduce cross-tenant data access accidentally. Tenant context should become explicit as the platform's authentication and authorization layers mature.

## Change Scope

When given a task:

1. Inspect the current implementation.
2. Reuse existing abstractions where possible.
3. Implement only the requested scope.
4. Add or update tests for changed behavior.
5. Update relevant documentation only when necessary.
6. Do not rewrite unrelated code.
7. Do not introduce speculative features.

## Git

Use Conventional Commits:

- `feat:` new functionality
- `fix:` bug fixes
- `refactor:` structural changes without behavior changes
- `test:` tests
- `docs:` documentation
- `build:` build/dependency changes
- `ci:` CI changes
- `chore:` maintenance

Keep commits focused and descriptive.

## Important

Before implementing a task, inspect the repository's current state. The GitHub repository is the source of truth. Do not assume that an older prompt or previous agent's implementation still exactly matches the current code.

Do not redesign the platform unless the task explicitly asks for an architectural change.
