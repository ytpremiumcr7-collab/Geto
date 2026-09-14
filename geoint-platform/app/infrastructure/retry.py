from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def is_retryable_exception(exc: Exception) -> bool:
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code

        return status in {
            408,
            425,
            429,
            500,
            502,
            503,
            504,
        }

    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
        ),
    )


def retryable():
    return retry(
        retry=retry_if_exception(is_retryable_exception),
        stop=stop_after_attempt(4),
        wait=wait_exponential(
            multiplier=1,
            min=1,
            max=30,
        ),
        reraise=True,
    )
