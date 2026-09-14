import httpx


class HttpClient:
    def __init__(
        self,
        timeout: float = 20,
        headers: dict[str, str] | None = None,
    ):
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        )

    async def get(self, *args, **kwargs):
        response = await self.client.get(*args, **kwargs)
        response.raise_for_status()
        return response

    async def post(self, *args, **kwargs):
        response = await self.client.post(*args, **kwargs)
        response.raise_for_status()
        return response

    async def close(self):
        await self.client.aclose()
