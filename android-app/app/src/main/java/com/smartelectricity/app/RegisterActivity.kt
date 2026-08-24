package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.AuthResponse
import com.smartelectricity.app.network.RegisterRequest
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class RegisterActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_register)

        // API Client Initialization
        api = ApiClient.api

        val etName = findViewById<EditText>(R.id.et_register_name)
        val etEmail = findViewById<EditText>(R.id.et_register_email)
        val etPassword = findViewById<EditText>(R.id.et_register_password)
        val etPhone = findViewById<EditText>(R.id.et_register_phone)
        val btnRegister = findViewById<Button>(R.id.btn_register)
        val tvLoginBack = findViewById<TextView>(R.id.tv_login_back)

        btnRegister.setOnClickListener {
            val name = etName.text.toString().trim()
            val email = etEmail.text.toString().trim()
            val password = etPassword.text.toString().trim()
            val phone = etPhone.text.toString().trim()

            if (name.isEmpty() || email.isEmpty() || password.isEmpty() || phone.isEmpty()) {
                Toast.makeText(this, "Please fill in all fields", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val request = RegisterRequest(name, email, password, phone)
            api.register(request).enqueue(object : Callback<AuthResponse> {
                override fun onResponse(call: Call<AuthResponse>, response: Response<AuthResponse>) {
                    if (response.isSuccessful && response.body() != null) {
                        val auth = response.body()!!
                        
                        // Save token in SharedPreferences
                        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
                        val edit = sharedPref.edit()
                        edit.putString("TOKEN", auth.token)
                        edit.putString("NAME", auth.user.name)
                        edit.putString("EMAIL", auth.user.email)
                        edit.apply()

                        Toast.makeText(this@RegisterActivity, "Registration Successful!", Toast.LENGTH_SHORT).show()

                        // Launch MainActivity
                        val intent = Intent(this@RegisterActivity, MainActivity::class.java)
                        intent.putExtra("TOKEN", auth.token)
                        intent.putExtra("NAME", auth.user.name)
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                        startActivity(intent)
                        finish()
                    } else {
                        Toast.makeText(this@RegisterActivity, "Registration Failed: Email already registered or invalid fields", Toast.LENGTH_LONG).show()
                    }
                }

                override fun onFailure(call: Call<AuthResponse>, t: Throwable) {
                    Toast.makeText(this@RegisterActivity, "Connection failed. Please ensure the backend server is running and check your network.", Toast.LENGTH_LONG).show()
                }
            })
        }

        tvLoginBack.setOnClickListener {
            finish()
        }
    }
}
