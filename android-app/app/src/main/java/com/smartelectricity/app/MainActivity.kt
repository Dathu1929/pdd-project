package com.smartelectricity.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.telephony.SmsManager
import android.view.GestureDetector
import android.view.MotionEvent
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var token: String? = null
    private val NOTIFICATION_CHANNEL_ID = "electricity_bill_alerts"
    private val SMS_PERMISSION_CODE = 101
    private val NOTIFICATION_PERMISSION_CODE = 202
    private var tts: TextToSpeech? = null
    private var isTtsReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webview)

        // Premium Dark App Status Bar to match sidebar & theme
        window.statusBarColor = android.graphics.Color.parseColor("#0A1224")

        // Create high-importance alert channel for notifications
        createNotificationChannel()

        // Initialize Android Native Text-to-Speech Engine for Multi-Language AI Voice Calling
        try {
            tts = TextToSpeech(this) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    isTtsReady = true
                    tts?.setPitch(1.0f)
                    tts?.setSpeechRate(0.92f)
                }
            }
        } catch (e: Exception) {
            isTtsReady = false
        }

        // Configure WebView settings
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.allowFileAccessFromFileURLs = true
        settings.allowUniversalAccessFromFileURLs = true

        // Bridge Native Android capabilities (Direct SIM SMS & System Status Bar Notifications)
        webView.addJavascriptInterface(WebAppInterface(), "AndroidNative")

        // Handle permissions for Android 13+ (Notifications)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_CODE)
            }
        }

        // Keep page navigation inside the app WebView instead of starting default browser
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                if (url == null) return false

                if (url.startsWith("sms:")) {
                    try {
                        val uri = Uri.parse(url)
                        val schemeSpecific = uri.schemeSpecificPart ?: ""
                        val number = schemeSpecific.substringBefore('?')
                        val body = uri.getQueryParameter("body") ?: ""
                        val smsIntent = Intent(Intent.ACTION_SENDTO).apply {
                            data = Uri.parse("smsto:$number")
                            putExtra("sms_body", body)
                            putExtra(Intent.EXTRA_TEXT, body)
                        }
                        startActivity(smsIntent)
                        return true
                    } catch (e: Exception) {
                        try {
                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                            startActivity(intent)
                            return true
                        } catch (e2: Exception) {
                            Toast.makeText(this@MainActivity, "Could not open messaging app: ${e2.message}", Toast.LENGTH_SHORT).show()
                            return true
                        }
                    }
                }

                if (url.startsWith("tel:") || url.startsWith("mailto:") || url.startsWith("whatsapp:")) {
                    try {
                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                        startActivity(intent)
                        return true
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Could not open app: ${e.message}", Toast.LENGTH_SHORT).show()
                        return true
                    }
                }
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
            }

            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                // If remote network connection timed out, seamlessly load the bundled offline assets!
                if (failingUrl != null && !failingUrl.startsWith("file:///")) {
                    Toast.makeText(this@MainActivity, "Network offline. Loading local standalone mode...", Toast.LENGTH_SHORT).show()
                    view?.loadUrl("file:///android_asset/index.html")
                }
            }
        }
        
        // Handle JavaScript alerts, confirms, etc.
        webView.webChromeClient = WebChromeClient()

        // Load the configured backend server URL
        loadServerUrl()

        // Configure long-press detection on WebView to open the Server Settings dialog
        val gestureDetector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onLongPress(e: MotionEvent) {
                showConfigureUrlDialog()
            }
        })

        webView.setOnTouchListener { _, event ->
            gestureDetector.onTouchEvent(event)
            false
        }

        // Handle incoming notification action on app launch
        handleNotificationAction(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNotificationAction(intent)
    }

    private fun handleNotificationAction(intent: Intent?) {
        val action = intent?.getStringExtra("NOTIFICATION_ACTION") ?: return
        if (action == "LIFT_CALL") {
            cancelCallNotification()
            runOnUiThread {
                webView.evaluateJavascript("if (typeof answerAICall === 'function') { answerAICall(); }", null)
            }
        } else if (action == "DECLINE_CALL") {
            cancelCallNotification()
            runOnUiThread {
                webView.evaluateJavascript("if (typeof endAICall === 'function') { endAICall(); }", null)
            }
        }
    }

    fun cancelCallNotification() {
        runOnUiThread {
            try {
                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                notificationManager.cancel(8888)
            } catch (e: Exception) {
                // Ignore
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "Electricity Bill Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Electricity bill dues, reminders and alerts"
                enableVibration(true)
            }
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    fun displaySystemNotification(title: String, message: String, actionType: String = "") {
        createNotificationChannel()
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val isIncomingCall = title.contains("Incoming Call", ignoreCase = true) || actionType == "LIFT_CALL"
        val effectiveAction = if (isIncomingCall) "LIFT_CALL" else actionType

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("NOTIFICATION_ACTION", effectiveAction)
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            (System.currentTimeMillis() % 10000).toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(R.drawable.app_logo)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)

        if (isIncomingCall) {
            val liftIntent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("NOTIFICATION_ACTION", "LIFT_CALL")
            }
            val liftPendingIntent = PendingIntent.getActivity(
                this,
                201,
                liftIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.addAction(0, "🟢 LIFT CALL", liftPendingIntent)

            val declineIntent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("NOTIFICATION_ACTION", "DECLINE_CALL")
            }
            val declinePendingIntent = PendingIntent.getActivity(
                this,
                202,
                declineIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.addAction(0, "🔴 DECLINE", declinePendingIntent)
        }

        val notificationId = if (isIncomingCall) 8888 else (System.currentTimeMillis() % 100000).toInt()
        notificationManager.notify(notificationId, builder.build())
    }

    inner class WebAppInterface {

        @JavascriptInterface
        fun sendDirectSMS(phoneNumber: String, message: String): String {
            val cleanNumber = phoneNumber.replace(Regex("[^0-9+]"), "")

            // Check if SEND_SMS permission is granted
            if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED) {
                runOnUiThread {
                    ActivityCompat.requestPermissions(
                        this@MainActivity,
                        arrayOf(Manifest.permission.SEND_SMS),
                        SMS_PERMISSION_CODE
                    )
                    // Fallback to opening SMS composer so user can immediately send with 1 click
                    try {
                        val smsIntent = Intent(Intent.ACTION_SENDTO).apply {
                            data = Uri.parse("smsto:$cleanNumber")
                            putExtra("sms_body", message)
                            putExtra(Intent.EXTRA_TEXT, message)
                        }
                        startActivity(smsIntent)
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Please allow SMS permission in Android settings", Toast.LENGTH_LONG).show()
                    }
                }
                return "PERMISSION_REQUESTED"
            }

            return try {
                val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    getSystemService(SmsManager::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    SmsManager.getDefault()
                }

                val parts = smsManager.divideMessage(message)
                if (parts.size > 1) {
                    smsManager.sendMultipartTextMessage(cleanNumber, null, parts, null, null)
                } else {
                    smsManager.sendTextMessage(cleanNumber, null, message, null, null)
                }

                runOnUiThread {
                    Toast.makeText(this@MainActivity, "⚡ Normal SMS sent to +91 $cleanNumber via SIM!", Toast.LENGTH_LONG).show()
                    displaySystemNotification("⚡ Normal SMS Dispatched", "Electricity bill alert delivered to +91 $cleanNumber")
                }
                "SENT"
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "SMS dispatch error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
                "ERROR: " + e.message
            }
        }

        @JavascriptInterface
        fun showNotification(title: String, message: String) {
            runOnUiThread {
                displaySystemNotification(title, message)
            }
        }

        @JavascriptInterface
        fun speakAI(text: String, langCode: String): String {
            return speakAIFallback(text, langCode, "")
        }

        @JavascriptInterface
        fun speakAIFallback(text: String, langCode: String, fallbackText: String): String {
            if (!isTtsReady || tts == null) {
                return "TTS_NOT_READY"
            }
            runOnUiThread {
                try {
                    val locale = when (langCode.lowercase()) {
                        "te", "te-in" -> Locale("te", "IN")
                        "hi", "hi-in" -> Locale("hi", "IN")
                        "ta", "ta-in" -> Locale("ta", "IN")
                        "kn", "kn-in" -> Locale("kn", "IN")
                        else -> Locale("en", "IN")
                    }
                    val res = tts?.setLanguage(locale)
                    var textToSpeak = text
                    if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
                        tts?.setLanguage(Locale("en", "IN"))
                        if (fallbackText.isNotBlank()) {
                            textToSpeak = fallbackText
                        }
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                        val params = Bundle().apply {
                            putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
                        }
                        tts?.speak(textToSpeak, TextToSpeech.QUEUE_FLUSH, params, "AIVoiceCall")
                    } else {
                        @Suppress("DEPRECATION")
                        val params = HashMap<String, String>().apply {
                            put(TextToSpeech.Engine.KEY_PARAM_VOLUME, "1.0")
                        }
                        @Suppress("DEPRECATION")
                        tts?.speak(textToSpeak, TextToSpeech.QUEUE_FLUSH, params)
                    }
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Voice playback: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
            return "SPEAKING"
        }

        @JavascriptInterface
        fun playCallConnectTone() {
            runOnUiThread {
                try {
                    val toneGen = android.media.ToneGenerator(android.media.AudioManager.STREAM_MUSIC, 100)
                    toneGen.startTone(android.media.ToneGenerator.TONE_PROP_BEEP, 200)
                } catch (e: Exception) {
                    // Ignore
                }
            }
        }

        @JavascriptInterface
        fun startCallVibrate() {
            runOnUiThread {
                try {
                    val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        vibrator?.vibrate(android.os.VibrationEffect.createWaveform(longArrayOf(0, 600, 800), 0))
                    } else {
                        @Suppress("DEPRECATION")
                        vibrator?.vibrate(longArrayOf(0, 600, 800), 0)
                    }
                } catch (e: Exception) {
                    // Ignore
                }
            }
        }

        @JavascriptInterface
        fun stopCallVibrate() {
            runOnUiThread {
                try {
                    val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator
                    vibrator?.cancel()
                } catch (e: Exception) {
                    // Ignore
                }
            }
        }

        @JavascriptInterface
        fun showMissedCallNotification(billNo: String, amount: String, dueDate: String) {
            runOnUiThread {
                displaySystemNotification(
                    "📞 Missed Call: Smart Electricity AI",
                    "You missed our bill due reminder. Bill #$billNo of ₹$amount is due on $dueDate."
                )
            }
        }

        @JavascriptInterface
        fun cancelCallNotification() {
            this@MainActivity.cancelCallNotification()
        }

        @JavascriptInterface
        fun stopAI(): Boolean {
            runOnUiThread {
                try {
                    tts?.stop()
                } catch (e: Exception) {
                    // Ignore
                }
            }
            return true
        }

        @JavascriptInterface
        fun isNativeApp(): Boolean {
            return true
        }
    }

    private fun loadServerUrl() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val serverUrl = sharedPref.getString("BACKEND_URL", "file:///android_asset/index.html") ?: "file:///android_asset/index.html"
        webView.loadUrl(serverUrl)
    }

    private fun showConfigureUrlDialog() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val currentUrl = sharedPref.getString("BACKEND_URL", "file:///android_asset/index.html") ?: "file:///android_asset/index.html"

        val input = EditText(this)
        input.setText(currentUrl)
        input.setPadding(32, 16, 32, 16)

        AlertDialog.Builder(this)
            .setTitle("Configure Server / Mode")
            .setMessage("Enter server URL (e.g. http://172.18.101.238:5000/ or http://10.0.2.2:5000/) or type 'local' for offline mode:")
            .setView(input)
            .setPositiveButton("Save") { _, _ ->
                var newUrl = input.text.toString().trim()
                if (newUrl.isEmpty() || newUrl.equals("local", ignoreCase = true)) {
                    newUrl = "file:///android_asset/index.html"
                }
                sharedPref.edit().putString("BACKEND_URL", newUrl).apply()
                webView.loadUrl(newUrl)
                Toast.makeText(this, "Target URL updated!", Toast.LENGTH_SHORT).show()
            }
            .setNeutralButton("Reset to Local") { _, _ ->
                val localUrl = "file:///android_asset/index.html"
                sharedPref.edit().putString("BACKEND_URL", localUrl).apply()
                webView.loadUrl(localUrl)
                Toast.makeText(this, "Loaded Local Standalone Mode!", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun isEmulator(): Boolean {
        val androidBuild = android.os.Build.FINGERPRINT
        return androidBuild.startsWith("generic") ||
                androidBuild.startsWith("unknown") ||
                android.os.Build.MODEL.contains("google_sdk") ||
                android.os.Build.MODEL.contains("Emulator") ||
                android.os.Build.MODEL.contains("Android SDK built for x86")
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        try {
            tts?.stop()
            tts?.shutdown()
        } catch (e: Exception) {
            // Ignore
        }
        super.onDestroy()
    }
}
