package sk.henkukaj.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class PushService : FirebaseMessagingService() {

    // Appka je otvorená: notifikáciu si zobrazíme sami (na pozadí ju ukáže systém).
    override fun onMessageReceived(m: RemoteMessage) {
        val n = m.notification ?: return
        vytvorKanal(this)
        val otvor = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            m.data["url"]?.let { putExtra("url", it) }
        }
        val pi = PendingIntent.getActivity(this, (System.currentTimeMillis() % 100000).toInt(), otvor,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val nb = NotificationCompat.Builder(this, "dealy")
            .setSmallIcon(R.drawable.ic_notif)
            .setColor(getColor(R.color.oranzova))
            .setContentTitle(n.title)
            .setContentText(n.body)
            .setAutoCancel(true)
            .setContentIntent(pi)
        getSystemService(NotificationManager::class.java)
            .notify((System.currentTimeMillis() % 100000).toInt(), nb.build())
    }

    companion object {
        fun vytvorKanal(c: Context) {
            if (Build.VERSION.SDK_INT < 26) return
            val nm = c.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel("dealy") == null) {
                nm.createNotificationChannel(
                    NotificationChannel("dealy", "Nové dealy", NotificationManager.IMPORTANCE_HIGH)
                        .apply { description = "Upozornenie na každý novo zverejnený deal" })
            }
        }
    }
}
