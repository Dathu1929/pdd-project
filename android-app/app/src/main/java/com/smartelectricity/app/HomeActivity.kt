package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import com.google.android.material.navigation.NavigationView

class HomeActivity : AppCompatActivity() {

    private lateinit var drawerLayout: DrawerLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        drawerLayout = findViewById(R.id.drawerLayout)
        val btnMenu = findViewById<ImageView>(R.id.btnMenu)
        val navigationView = findViewById<NavigationView>(R.id.navigationView)

        // Find buttons and layouts
        val btnViewBillPay = findViewById<Button>(R.id.btnViewBillPay)
        val btnQuickPay = findViewById<LinearLayout>(R.id.btnQuickPay)
        val btnQuickDownload = findViewById<LinearLayout>(R.id.btnQuickDownload)
        val btnQuickHistory = findViewById<LinearLayout>(R.id.btnQuickHistory)
        val btnQuickAdd = findViewById<LinearLayout>(R.id.btnQuickAdd)

        btnMenu.setOnClickListener {
            drawerLayout.openDrawer(GravityCompat.START)
        }

        // Set Click Listeners
        btnViewBillPay.setOnClickListener {
            val intent = Intent(this, MainActivity::class.java)
            startActivity(intent)
        }

        btnQuickPay.setOnClickListener {
            val intent = Intent(this, MainActivity::class.java)
            startActivity(intent)
        }

        btnQuickDownload.setOnClickListener {
            Toast.makeText(this, "Downloading Bill...", Toast.LENGTH_SHORT).show()
        }

        btnQuickHistory.setOnClickListener {
            val intent = Intent(this, HistoryActivity::class.java)
            startActivity(intent)
        }

        btnQuickAdd.setOnClickListener {
            val intent = Intent(this, AddConnectionActivity::class.java)
            startActivity(intent)
        }

        navigationView.setNavigationItemSelectedListener { menuItem ->
            when (menuItem.itemId) {
                R.id.nav_home -> {
                    // Already here
                }
                R.id.nav_connections -> {
                    startActivity(Intent(this, AddConnectionActivity::class.java))
                }
                R.id.nav_bills -> {
                    startActivity(Intent(this, HistoryActivity::class.java))
                }
                R.id.nav_payments -> {
                    startActivity(Intent(this, MainActivity::class.java))
                }
                R.id.nav_analytics -> {
                    Toast.makeText(this, "Analytics Dashboard", Toast.LENGTH_SHORT).show()
                }
                R.id.nav_reminders -> {
                    startActivity(Intent(this, RemindersActivity::class.java))
                }
                R.id.nav_profile -> {
                    startActivity(Intent(this, ProfileActivity::class.java))
                }
                R.id.nav_logout -> {
                    val intent = Intent(this, LoginActivity::class.java)
                    intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                    startActivity(intent)
                    finish()
                }
            }
            drawerLayout.closeDrawer(GravityCompat.START)
            true
        }
    }

    override fun onBackPressed() {
        if (drawerLayout.isDrawerOpen(GravityCompat.START)) {
            drawerLayout.closeDrawer(GravityCompat.START)
        } else {
            super.onBackPressed()
        }
    }
}
