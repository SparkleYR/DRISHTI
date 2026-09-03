package com.drishti.app.net

import retrofit2.Response

/** Normalised outcome of a backend call. */
sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>

    /** Backend returned the typed error envelope (HTTP 4xx/5xx with a body). */
    data class Failure(
        val code: String,
        val message: String,
        val retryable: Boolean,
        val httpStatus: Int,
    ) : ApiResult<Nothing>

    /** No usable HTTP response: DNS, connect, timeout, TLS, socket reset. */
    data class Transport(val cause: Throwable) : ApiResult<Nothing> {
        val message: String get() = cause.message ?: cause.javaClass.simpleName
    }
}

inline fun <T> ApiResult<T>.onOk(block: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Ok) block(value)
    return this
}

fun <T> ApiResult<T>.valueOrNull(): T? = (this as? ApiResult.Ok)?.value

/** Wrap a Retrofit suspend call, decoding the DRISHTI error envelope on failure. */
suspend fun <T> apiCall(block: suspend () -> Response<T>): ApiResult<T> =
    try {
        val response = block()
        val body = response.body()
        if (response.isSuccessful && body != null) {
            ApiResult.Ok(body)
        } else if (response.isSuccessful) {
            ApiResult.Failure("EMPTY_BODY", "Empty response body.", retryable = true, response.code())
        } else {
            val raw = response.errorBody()?.string().orEmpty()
            val envelope = runCatching { DrishtiJson.decodeFromString<ApiErrorResponse>(raw) }.getOrNull()
            if (envelope != null) {
                ApiResult.Failure(
                    code = envelope.error.code,
                    message = envelope.error.message,
                    retryable = envelope.error.retryable,
                    httpStatus = response.code(),
                )
            } else {
                ApiResult.Failure(
                    code = "HTTP_${response.code()}",
                    message = "Backend returned HTTP ${response.code()}.",
                    retryable = response.code() >= 500,
                    httpStatus = response.code(),
                )
            }
        }
    } catch (ce: kotlinx.coroutines.CancellationException) {
        throw ce
    } catch (t: Throwable) {
        ApiResult.Transport(t)
    }
