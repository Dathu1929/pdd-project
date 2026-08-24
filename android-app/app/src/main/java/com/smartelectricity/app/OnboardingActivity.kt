package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity

class OnboardingActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_onboarding)

        val btnGetStarted = findViewById<Button>(R.id.btn_get_started)
        val btnSkip = findViewById<Button>(R.id.btn_skip)

        val navigateToLogin = {
            val intent = Intent(this, LoginActivity::class.java)
            startActivity(intent)
            finish()
        }

        btnGetStarted.setOnClickListener { navigateToLogin() }
        btnSkip.setOnClickListener { navigateToLogin() }
    }
}
