package sk.henkukaj.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.net.URL

class PushService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        Prefs.setToken(this, token)
    }

    // Správy chodia len ako "data", takže notifikáciu skladáme (a filtrujeme)
    // vždy my - aj keď je appka zatvorená.
    override fun onMessageReceived(m: RemoteMessage) {
        val d = m.data
        val title = d["title"] ?: return
        val typ = d["typ"] ?: "dealy"
        if (typ == "straz") {
            if (!Prefs.pushStraz(this)) return
        } else {
            if (!Prefs.pushDealy(this)) return
            val kat = d["kategoria"] ?: ""
            if (kat.isNotEmpty() && kat !in Prefs.temy(this)) return
            val zlava = d["zlava"]?.toIntOrNull() ?: 0
            if (zlava < Prefs.minZlava(this)) return
        }
        vytvorKanal(this)
        val otvor = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            d["url"]?.let { putExtra("url", it) }
        }
        val id = (System.currentTimeMillis() % 100000).toInt()
        val pi = PendingIntent.getActivity(
            this, id, otvor,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val nb = NotificationCompat.Builder(this, "dealy")
            .setSmallIcon(R.drawable.ic_notif)
            .setColor(getColor(R.color.oranzova))
            .setContentTitle(title)
            .setContentText(d["body"])
            .setAutoCancel(true)
            .setContentIntent(pi)
        obrazok(d["image"])?.let {
            nb.setLargeIcon(it)
            nb.setStyle(NotificationCompat.BigPictureStyle().bigPicture(it).bigLargeIcon(null as Bitmap?))
        }
        getSystemService(NotificationManager::class.java).notify(id, nb.build())
    }

    // Fotka dealu je len ozdoba - keď sa nestiahne, notifikácia ide bez nej.
    private fun obrazok(url: String?): Bitmap? {
        if (url.isNullOrBlank() || !url.startsWith("https://")) return null
        return try {
            val c = URL(url).openConnection().apply { connectTimeout = 4000; readTimeout = 4000 }
            BitmapFactory.decodeStream(c.getInputStream())
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        fun vytvorKanal(c: Context) {
            if (Build.VERSION.SDK_INT < 26) return
            val nm = c.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel("dealy") == null) {
                nm.createNotificationChannel(
                    NotificationChannel("dealy", "Nové dealy", NotificationManager.IMPORTANCE_HIGH)
                        .apply { description = "Nové dealy, Stráž ceny a letenky" }
                )
            }
        }
    }
}
