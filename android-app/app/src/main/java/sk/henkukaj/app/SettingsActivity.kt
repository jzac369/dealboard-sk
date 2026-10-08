package sk.henkukaj.app

import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.biometric.BiometricManager
import androidx.core.content.ContextCompat

// Nastavenia bez cudzích knižníc. Písmo je zámerne malé (14 sp nadpis, 12 sp popis).
class SettingsActivity : AppCompatActivity() {

    private val oranz by lazy { ContextCompat.getColor(this, R.color.oranzova) }
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Nastavenia"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        build()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun build() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, dp(24))
        }

        col.addView(sekcia("Notifikácie"))
        col.addView(prepinac("Nové dealy", "Predvolene zapnuté", Prefs.pushDealy(this)) { Prefs.setPushDealy(this, it) })
        col.addView(popis("Témy"))
        val vybrane = Prefs.temy(this).toMutableSet()
        Prefs.TEMY.forEach { (kluc, nazov) ->
            val cb = CheckBox(this).apply {
                text = nazov
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                isChecked = kluc in vybrane
                buttonTintList = ColorStateList.valueOf(oranz)
                setOnCheckedChangeListener { _, ch ->
                    if (ch) vybrane.add(kluc) else vybrane.remove(kluc)
                    Prefs.setTemy(this@SettingsActivity, vybrane.toSet())
                }
            }
            col.addView(cb, LinearLayout.LayoutParams(-1, -2).apply { marginStart = dp(12) })
        }

        val zlava = riadok("Len zľava od", textZlavy(), null)
        zlava.root.setOnClickListener {
            val moznosti = intArrayOf(0, 20, 30, 40, 50)
            AlertDialog.Builder(this).setTitle("Len zľava od")
                .setSingleChoiceItems(
                    moznosti.map { if (it == 0) "Všetky dealy" else "$it %" }.toTypedArray(),
                    moznosti.indexOf(Prefs.minZlava(this)).coerceAtLeast(0)
                ) { d, i ->
                    Prefs.setMinZlava(this, moznosti[i])
                    zlava.pod.text = textZlavy()
                    d.dismiss()
                }.show()
        }
        col.addView(zlava.root)

        col.addView(sekcia("Stráž ceny a letenky"))
        col.addView(prepinac("Upozornenia", "Stráž ceny a lacné letenky ako push", Prefs.pushStraz(this)) {
            Prefs.setPushStraz(this, it)
        })
        col.addView(riadok("Upraviť Stráž ceny", "otvorí tvoj účet", "›").root.apply { setOnClickListener { otvorUcet() } })
        col.addView(riadok("Letiská a max. cena letenky", "otvorí tvoj účet", "›").root.apply { setOnClickListener { otvorUcet() } })

        col.addView(sekcia("Účet a zabezpečenie"))
        val mozeBio = BiometricManager.from(this)
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) == BiometricManager.BIOMETRIC_SUCCESS
        val bio = prepinac(
            "Zamknúť appku odtlačkom",
            if (mozeBio) "odtlačok pri otvorení appky" else "toto zariadenie nemá nastavený odtlačok",
            Prefs.zamok(this) && mozeBio
        ) { Prefs.setZamok(this, it) }
        if (!mozeBio) bio.getChildAt(1).isEnabled = false
        col.addView(bio)
        col.addView(popis("Verzia " + packageManager.getPackageInfo(packageName, 0).versionName))

        setContentView(ScrollView(this).apply {
            setBackgroundColor(Color.WHITE)
            addView(col)
        })
    }

    private fun textZlavy() = Prefs.minZlava(this).let { if (it == 0) "všetky dealy" else "od $it %" }

    private fun otvorUcet() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("url", "https://henkukaj.sk/?ucet=nastavenia")
        })
        finish()
    }

    private fun sekcia(t: String) = TextView(this).apply {
        text = t.uppercase()
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
        setTextColor(oranz)
        typeface = Typeface.DEFAULT_BOLD
        letterSpacing = 0.05f
        setPadding(dp(16), dp(20), dp(16), dp(6))
    }

    private fun popis(t: String) = TextView(this).apply {
        text = t
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
        setTextColor(Color.GRAY)
        setPadding(dp(16), dp(8), dp(16), dp(4))
    }

    private class Riadok(val root: LinearLayout, val pod: TextView)

    private fun riadok(nadpis: String, pod: String, vpravo: String?): Riadok {
        val r = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(10), dp(16), dp(10))
            minimumHeight = dp(48)
            isClickable = true
            isFocusable = true
            setBackgroundResource(android.R.drawable.list_selector_background)
        }
        val l = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        l.addView(TextView(this).apply {
            text = nadpis
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(Color.parseColor("#1A1A1A"))
        })
        val p = TextView(this).apply {
            text = pod
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTextColor(Color.GRAY)
        }
        l.addView(p)
        r.addView(l, LinearLayout.LayoutParams(0, -2, 1f))
        if (vpravo != null) r.addView(TextView(this).apply {
            text = vpravo
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setTextColor(Color.GRAY)
        })
        return Riadok(r, p)
    }

    private fun prepinac(nadpis: String, pod: String, zap: Boolean, zmena: (Boolean) -> Unit): LinearLayout {
        val r = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
            minimumHeight = dp(48)
        }
        val l = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        l.addView(TextView(this).apply {
            text = nadpis
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(Color.parseColor("#1A1A1A"))
        })
        l.addView(TextView(this).apply {
            text = pod
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTextColor(Color.GRAY)
        })
        r.addView(l, LinearLayout.LayoutParams(0, -2, 1f))
        r.addView(SwitchCompat(this).apply {
            isChecked = zap
            setOnCheckedChangeListener { _, v -> zmena(v) }
            thumbTintList = ColorStateList.valueOf(oranz)
            trackTintList = ColorStateList.valueOf(Color.parseColor("#F5C4A3"))
        })
        return r
    }
}
