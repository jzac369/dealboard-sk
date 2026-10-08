package sk.henkukaj.app

import android.content.Context

object Prefs {
    private fun p(c: Context) = c.getSharedPreferences("nastavenia", Context.MODE_PRIVATE)

    // Témy zodpovedajú kategóriám dealov na stránke.
    val TEMY = linkedMapOf(
        "Elektronika" to "Elektronika",
        "Jedlo & Nápoje" to "Potraviny a nápoje",
        "Dom & Záhrada" to "Dom a záhrada",
        "Móda" to "Móda",
        "Šport" to "Šport",
        "Hračky" to "Hračky",
        "Cestovanie" to "Cestovanie a letenky",
        "Iné" to "Ostatné",
    )

    fun pushDealy(c: Context) = p(c).getBoolean("push_dealy", true)
    fun setPushDealy(c: Context, v: Boolean) = p(c).edit().putBoolean("push_dealy", v).apply()

    fun temy(c: Context): Set<String> = p(c).getStringSet("temy", TEMY.keys) ?: TEMY.keys
    fun setTemy(c: Context, v: Set<String>) = p(c).edit().putStringSet("temy", v).apply()

    fun minZlava(c: Context) = p(c).getInt("min_zlava", 0)
    fun setMinZlava(c: Context, v: Int) = p(c).edit().putInt("min_zlava", v).apply()

    fun pushStraz(c: Context) = p(c).getBoolean("push_straz", true)
    fun setPushStraz(c: Context, v: Boolean) = p(c).edit().putBoolean("push_straz", v).apply()

    fun zamok(c: Context) = p(c).getBoolean("zamok", false)
    fun setZamok(c: Context, v: Boolean) = p(c).edit().putBoolean("zamok", v).apply()

    fun token(c: Context) = p(c).getString("fcm_token", "") ?: ""
    fun setToken(c: Context, v: String) = p(c).edit().putString("fcm_token", v).apply()
}
