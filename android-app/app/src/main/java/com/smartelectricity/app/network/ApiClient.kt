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

    private fun isEmulator(): Boolean {
        val brand = android.os.Build.BRAND
        val device = android.os.Build.DEVICE
        val fingerprint = android.os.Build.FINGERPRINT
        val hardware = android.os.Build.HARDWARE
        val model = android.os.Build.MODEL
        val manufacturer = android.os.Build.MANUFACTURER
        val product = android.os.Build.PRODUCT
        
        return (brand.startsWith("generic") && device.startsWith("generic"))
                || fingerprint.startsWith("generic")
                || fingerprint.startsWith("unknown")
                || hardware.contains("goldfish")
                || hardware.contains("ranchu")
                || model.contains("google_sdk")
                || model.contains("Emulator")
                || model.contains("Android SDK built for x86")
                || manufacturer.contains("Genymotion")
                || product.contains("sdk_google")
                || product.contains("google_sdk")
                || product.contains("sdk")
                || product.contains("sdk_x86")
                || product.contains("vbox86p")
                || product.contains("emulator")
                || product.contains("simulator")
    }

    private fun getDefaultUrl(): String {
        return if (isEmulator()) "http://10.0.2.2:8000/" else "http://192.168.137.87:8000/"
    }

    fun initialize(context: Context) {
        val defaultUrl = getDefaultUrl()
        val sharedPref = context.getSharedPreferences("SmartElectricityPrefs", Context.MODE_PRIVATE)
        var savedUrl = sharedPref.getString("BACKEND_URL", defaultUrl) ?: defaultUrl
        
        if (!isEmulator() && (savedUrl.contains("127.0.0.1") || savedUrl.contains("10.0.2.2"))) {
            savedUrl = defaultUrl
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
