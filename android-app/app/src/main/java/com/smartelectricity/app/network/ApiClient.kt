package com.smartelectricity.app.network

import android.content.Context
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    private var currentUrl = "http://192.168.137.87:8000/"
    private var retrofit: Retrofit? = null

    val api: ApiInterface
        get() {
            if (retrofit == null) {
                retrofit = Retrofit.Builder()
                    .baseUrl(currentUrl)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build()
            }
            return retrofit!!.create(ApiInterface::class.java)
        }

    fun initialize(context: Context) {
        val sharedPref = context.getSharedPreferences("SmartElectricityPrefs", Context.MODE_PRIVATE)
        var savedUrl = sharedPref.getString("BACKEND_URL", "http://192.168.137.87:8000/") ?: "http://192.168.137.87:8000/"
        if (savedUrl.contains("127.0.0.1") || savedUrl.contains("10.0.2.2")) {
            savedUrl = "http://192.168.137.87:8000/"
            sharedPref.edit().putString("BACKEND_URL", savedUrl).apply()
        }
        updateUrl(savedUrl)
    }

    fun updateUrl(newUrl: String) {
        val formattedUrl = if (newUrl.endsWith("/")) newUrl else "$newUrl/"
        currentUrl = formattedUrl
        retrofit = Retrofit.Builder()
            .baseUrl(formattedUrl)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }
}
