package com.smartelectricity.app

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.edit
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.AuthResponse
import com.smartelectricity.app.network.LoginRequest
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class LoginActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface

    @SuppressLint("SetTextI18n")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Dynamic API Client Base URL
        ApiClient.initialize(this)
        api = ApiClient.api

        setContentView(R.layout.activity_login)

        val etEmail = findViewById<EditText>(R.id.et_email)
        val etPassword = findViewById<EditText>(R.id.et_password)
        val btnLogin = findViewById<Button>(R.id.btn_login)
        val tvRegister = findViewById<TextView>(R.id.tv_register)
        val ivHeaderBg = findViewById<ImageView>(R.id.iv_header_bg)

        // Prepopulate with last saved email or fallback to test user
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val savedEmail = sharedPref.getString("EMAIL", "dattu@gmail.com")
        etEmail.setText(savedEmail)
        if (savedEmail == "dattu@gmail.com") {
            etPassword.setText("dattu123")
        } else {
            etPassword.setText("")
        }

        // Long-click the header image to change the Backend Server URL (e.g. for different Wi-Fi / Ngrok)
        ivHeaderBg.setOnLongClickListener {
            showConfigureUrlDialog()
            true
        }

        btnLogin.setOnClickListener {
            val email = etEmail.text.toString().trim()
            val password = etPassword.text.toString().trim()

            if (email.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "Fields cannot be empty", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // Ensure we use the latest api instance (in case the base URL was modified)
            api = ApiClient.api

            api.login(LoginRequest(email, password)).enqueue(object : Callback<AuthResponse> {
                override fun onResponse(call: Call<AuthResponse>, response: Response<AuthResponse>) {
                    if (response.isSuccessful && response.body() != null) {
                        val auth = response.body()!!
                        
                        // Save authentication details locally
                        getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE).edit {
                            putString("TOKEN", auth.token)
                            putString("NAME", auth.user.name)
                            putString("EMAIL", auth.user.email)
                        }

                        // Navigate to Home Dashboard
                        val intent = Intent(this@LoginActivity, MainActivity::class.java)
                        intent.putExtra("TOKEN", auth.token)
                        intent.putExtra("NAME", auth.user.name)
                        startActivity(intent)
                        finish()
                    } else {
                        Toast.makeText(this@LoginActivity, "Invalid email/phone or password", Toast.LENGTH_SHORT).show()
                    }
                }

                override fun onFailure(call: Call<AuthResponse>, t: Throwable) {
                    val currentUrl = sharedPref.getString("BACKEND_URL", "http://192.168.137.87:8000/")
                    Toast.makeText(this@LoginActivity, "Connection failed to $currentUrl. Long-press top banner to configure.", Toast.LENGTH_LONG).show()
                }
            })
        }

        tvRegister.setOnClickListener {
            val intent = Intent(this, RegisterActivity::class.java)
            startActivity(intent)
        }
    }

    private fun showConfigureUrlDialog() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val currentUrl = sharedPref.getString("BACKEND_URL", "http://192.168.137.87:8000/")

        val input = EditText(this)
        input.setText(currentUrl)
        input.setPadding(32, 16, 32, 16)

        AlertDialog.Builder(this)
            .setTitle("Configure Server URL")
            .setMessage("Enter the backend server address (e.g. http://192.168.1.100:8000/ or your Ngrok public URL):")
            .setView(input)
            .setPositiveButton("Save") { _, _ ->
                val newUrl = input.text.toString().trim()
                if (newUrl.isNotEmpty()) {
                    sharedPref.edit().putString("BACKEND_URL", newUrl).apply()
                    ApiClient.updateUrl(newUrl)
                    api = ApiClient.api
                    Toast.makeText(this, "Server URL updated to: $newUrl", Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
