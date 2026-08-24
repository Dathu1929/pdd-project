package com.smartelectricity.app

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
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

        // Auto-login check commented out to prevent auto-skipping the login page
        /*
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val savedToken = sharedPref.getString("TOKEN", null)
        if (savedToken != null) {
            val intent = Intent(this, MainActivity::class.java)
            intent.putExtra("TOKEN", savedToken)
            intent.putExtra("NAME", sharedPref.getString("NAME", ""))
            startActivity(intent)
            finish()
            return
        }
        */

        setContentView(R.layout.activity_login)

        // API Client Initialization
        api = ApiClient.api

        val etEmail = findViewById<EditText>(R.id.et_email)
        val etPassword = findViewById<EditText>(R.id.et_password)
        val btnLogin = findViewById<Button>(R.id.btn_login)
        val tvRegister = findViewById<TextView>(R.id.tv_register)

        // Prepopulate with last saved email or fallback to test user
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        // noinspection SpellCheckingInspection
        val savedEmail = sharedPref.getString("EMAIL", "dattu@gmail.com")
        etEmail.setText(savedEmail)
        // noinspection SpellCheckingInspection
        if (savedEmail == "dattu@gmail.com") {
            // noinspection SpellCheckingInspection
            etPassword.setText("dattu123")
        } else {
            etPassword.setText("")
        }

        btnLogin.setOnClickListener {
            val email = etEmail.text.toString().trim()
            val password = etPassword.text.toString().trim()

            if (email.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "Fields cannot be empty", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

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
                    Toast.makeText(this@LoginActivity, "Connection failed. Please ensure the backend server is running and check your network.", Toast.LENGTH_LONG).show()
                }
            })
        }

        tvRegister.setOnClickListener {
            val intent = Intent(this, RegisterActivity::class.java)
            startActivity(intent)
        }
    }
}
