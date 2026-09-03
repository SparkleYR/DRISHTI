package com.drishti.app.net

import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

/**
 * Holds the user-configured backend origin. The base URL is editable at runtime
 * from Settings, so a single OkHttp/Retrofit instance is kept and every request
 * is rewritten to the current origin by [BaseUrlInterceptor].
 */
object BackendOrigin {
    @Volatile
    var url: HttpUrl? = null

    fun set(raw: String): Boolean {
        val normalized = raw.trim().let { if (it.startsWith("http")) it else "http://$it" }
        val parsed = normalized.toHttpUrlOrNull() ?: return false
        url = parsed
        return true
    }
}

private class BaseUrlInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val target = BackendOrigin.url ?: return chain.proceed(request)
        val newUrl = request.url.newBuilder()
            .scheme(target.scheme)
            .host(target.host)
            .port(target.port)
            .build()
        return chain.proceed(request.newBuilder().url(newUrl).build())
    }
}

/**
 * The local VLM reloads Moondream2 from disk on every request, so `/vlm/query`
 * and `/vlm/locate` legitimately take many seconds (backend timeout is 45 s).
 * Widen only those calls' read timeout; every other endpoint keeps the tight 30 s budget.
 */
private class VlmTimeoutInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val path = request.url.encodedPath
        if (!path.endsWith("/vlm/query") && !path.endsWith("/vlm/locate")) {
            return chain.proceed(request)
        }
        return chain
            .withReadTimeout(70, TimeUnit.SECONDS)
            .withWriteTimeout(30, TimeUnit.SECONDS)
            .proceed(request)
    }
}

object ApiModule {

    @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
    fun create(debug: Boolean): DrishtiApi {
        val client = OkHttpClient.Builder()
            .addInterceptor(BaseUrlInterceptor())
            .addInterceptor(VlmTimeoutInterceptor())
            .apply {
                if (debug) {
                    addInterceptor(
                        HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC },
                    )
                }
            }
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

        return Retrofit.Builder()
            // Placeholder; every call is retargeted by BaseUrlInterceptor.
            .baseUrl("http://drishti.invalid/")
            .client(client)
            .addConverterFactory(DrishtiJson.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(DrishtiApi::class.java)
    }
}
