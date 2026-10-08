package sk.henkukaj.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewAnimationUtils
import android.view.animation.DecelerateInterpolator
import android.view.animation.LinearInterpolator
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.firebase.messaging.FirebaseMessaging

class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var obnov: SwipeRefreshLayout
    private lateinit var uvod: FrameLayout
    private var stranka = false
    private var animaciaHotova = false

    private val povolenie = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        web = findViewById(R.id.web)
        obnov = findViewById(R.id.obnov)
        uvod = findViewById(R.id.uvod)

        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.userAgentString = web.settings.userAgentString + " HenKukajApp/1.0"
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean {
                val host = r.url.host ?: return false
                if (host == "henkukaj.sk" || host.endsWith(".henkukaj.sk")) return false
                // Obchody a iné weby sa otvoria v prehliadači, nie v appke.
                startActivity(Intent(Intent.ACTION_VIEW, r.url))
                return true
            }
            override fun onPageFinished(v: WebView, url: String?) {
                obnov.isRefreshing = false
                stranka = true
                skryUvod()
            }
        }
        obnov.setColorSchemeResources(R.color.oranzova)
        obnov.setOnRefreshListener { web.reload() }
        obnov.setOnChildScrollUpCallback { _, _ -> web.scrollY > 0 }

        pustiAnimaciuLoga()
        nacitaj(intent)
        zapniNotifikacie()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        nacitaj(intent)
    }

    // Klepnutie na notifikáciu prinesie adresu dealu; inak sa otvorí úvod.
    private fun nacitaj(i: Intent?) {
        val url = i?.getStringExtra("url") ?: i?.data?.toString() ?: "https://henkukaj.sk/"
        web.loadUrl(url)
    }

    // Úvod: obrázok sa "odkryje" kruhom od stredu lupy (kohút vykukne zo tmy)
    // a pomaly sa približuje, kým sa načíta stránka.
    private fun pustiAnimaciuLoga() {
        val logo = findViewById<ImageView>(R.id.logo)
        val verzia = findViewById<TextView>(R.id.verzia)
        verzia.text = "ver. " + packageManager.getPackageInfo(packageName, 0).versionName
        verzia.animate().alpha(1f).setStartDelay(700).setDuration(500).start()
        logo.post {
            val vw = logo.width.toFloat(); val vh = logo.height.toFloat()
            val s = maxOf(vw / 853f, vh / 1844f)
            val cx = ((410f * s) - (853f * s - vw) / 2f).toInt()
            val cy = ((515f * s) - (1844f * s - vh) / 2f).toInt()
            val r = Math.hypot(vw.toDouble(), vh.toDouble()).toFloat()
            logo.visibility = View.INVISIBLE
            val reveal = ViewAnimationUtils.createCircularReveal(logo, cx, cy, 0f, r)
            reveal.duration = 850
            reveal.interpolator = DecelerateInterpolator(1.3f)
            logo.visibility = View.VISIBLE
            reveal.start()
            logo.pivotX = cx.toFloat(); logo.pivotY = cy.toFloat()
            logo.animate().scaleX(1.07f).scaleY(1.07f).setDuration(2200)
                .setInterpolator(LinearInterpolator()).start()
            logo.postDelayed({ animaciaHotova = true; skryUvod() }, 1500)
        }
    }

    // Úvod zmizne, keď dobehla animácia aj prvá stránka (aspoň ~1,2 s celkom).
    private fun skryUvod() {
        if (!(stranka && animaciaHotova) || uvod.visibility != View.VISIBLE) return
        uvod.postDelayed({
            uvod.animate().alpha(0f).setDuration(350).withEndAction { uvod.visibility = View.GONE }.start()
        }, 250)
    }

    // Notifikácie sú predvolene zapnuté: prihlásenie na tému "dealy" pri prvom
    // spustení. Android 13+ navyše vyžaduje súhlas používateľa v dialógu.
    private fun zapniNotifikacie() {
        PushService.vytvorKanal(this)
        FirebaseMessaging.getInstance().subscribeToTopic("dealy")
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            povolenie.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
