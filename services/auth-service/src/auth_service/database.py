"""MongoDB wiring for the auth service."""

import os

from pymongo import AsyncMongoClient

from auth_service.repositories import AuthAccountRepository


DEFAULT_AUTH_DATABASE = "call_e_auth"
MONGODB_URL_ENV_VAR = "MONGODB_URL"
AUTH_DATABASE_ENV_VAR = "AUTH_DATABASE_NAME"


class AuthDatabase:
    """Own the auth service's MongoDB client lifecycle."""

    def __init__(self, *, mongodb_url: str, database_name: str) -> None:
        self._client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=1_000)
        self.repository = AuthAccountRepository(self._client[database_name])

    async def close(self) -> None:
        """Release the MongoDB client during application shutdown."""
        await self._client.close()


def create_auth_database() -> AuthDatabase:
    """Build the auth database boundary from service runtime configuration."""
    mongodb_url = os.getenv(MONGODB_URL_ENV_VAR, "mongodb://localhost:27017")
    database_name = os.getenv(AUTH_DATABASE_ENV_VAR, DEFAULT_AUTH_DATABASE)
    return AuthDatabase(mongodb_url=mongodb_url, database_name=database_name)
