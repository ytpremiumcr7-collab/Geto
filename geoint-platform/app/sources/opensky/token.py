import time

import httpx

from app.core.config import settings


class OpenSkyTokenManager:
    def __init__(self):
        self.token: str | None = None
        self.expires_at: float = 0

    async def get_token(self) -> str:

        now = time.time()

        if self.token and now < self.expires_at - 60:
            return self.token

        if not settings.opensky_client_id:
            raise RuntimeError("OPENSKY_CLIENT_ID is not configured")

        if not settings.opensky_client_secret:
            raise RuntimeError("OPENSKY_CLIENT_SECRET is not configured")

        async with httpx.AsyncClient(timeout=settings.opensky_timeout_seconds) as client:
            response = await client.post(
                settings.opensky_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.opensky_client_id,
                    "client_secret": settings.opensky_client_secret,
                },
            )

            response.raise_for_status()

            data = response.json()

        self.token = data["access_token"]

        self.expires_at = now + data.get("expires_in", 1800)

        return self.token
