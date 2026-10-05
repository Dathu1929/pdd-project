package com.smartelectricity.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val etServerUrl = findViewById<EditText>(R.id.etServerUrl)
        val btnSaveSettings = findViewById<Button>(R.id.btnSaveSettings)
        val btnLogout = findViewById<Button>(R.id.btnLogout)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", Context.MODE_PRIVATE)
        val currentUrl = sharedPref.getString("BACKEND_URL", "http://192.168.137.87:8000/")
        etServerUrl.setText(currentUrl)

        btnSaveSettings.setOnClickListener {
            val newUrl = etServerUrl.text.toString().trim()
            if (newUrl.isNotEmpty()) {
                sharedPref.edit().putString("BACKEND_URL", newUrl).apply()
                Toast.makeText(this, "Configuration Saved!", Toast.LENGTH_SHORT).show()
                finish()
            }
        }

        btnLogout.setOnClickListener {
            val intent = Intent(this, LoginActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            startActivity(intent)
            finish()
        }
    }
}
