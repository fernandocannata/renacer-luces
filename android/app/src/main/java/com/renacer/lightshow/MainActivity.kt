package com.renacer.lightshow

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.wifi.WifiManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException

/**
 * LightShow Remoto: busca la PC con Renacer LightShow en el mismo Wi-Fi
 * y muestra su página de control remoto a pantalla completa.
 */
class MainActivity : Activity() {

    companion object {
        const val DISCOVERY_PORT = 8733
        const val DEFAULT_PORT = 8731
        const val ASK = "RENACER_LIGHTSHOW?"
        const val BG = 0xFF0F0C13.toInt()
        const val PANEL = 0xFF1A1520.toInt()
        const val CTRL = 0xFF2A2331.toInt()
        const val LINE = 0xFF342B3D.toInt()
        const val TEXT = 0xFFF2EBDF.toInt()
        const val MUTED = 0xFFA99EAD.toInt()
        const val AMBER = 0xFFD9A55B.toInt()
        const val AMBER_INK = 0xFF241504.toInt()
    }

    private data class Pc(val name: String, val host: String, val show: String, val version: String)

    private val main = Handler(Looper.getMainLooper())
    private lateinit var web: WebView
    private lateinit var connectBox: View
    private lateinit var status: TextView
    private lateinit var found: LinearLayout
    private lateinit var searchBtn: Button
    private lateinit var addr: EditText
    private var currentHost: String? = null
    private var searching = false
    private var lastBack = 0L

    private val prefs by lazy { getSharedPreferences("remoto", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val root = FrameLayout(this).apply { setBackgroundColor(BG) }
        web = buildWeb()
        connectBox = buildConnect()
        root.addView(web, FrameLayout.LayoutParams(-1, -1))
        root.addView(connectBox, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)

        val saved = prefs.getString("host", null)
        if (saved != null) {
            addr.setText(saved)
            open(saved)
        } else {
            showConnect(null)
        }
    }

    // ------------------------------------------------------------------ WebView

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    private fun buildWeb(): WebView {
        val w = WebView(this)
        w.setBackgroundColor(BG)
        w.settings.javaScriptEnabled = true
        w.settings.domStorageEnabled = true
        w.settings.mediaPlaybackRequiresUserGesture = false
        w.settings.setSupportZoom(false)
        w.settings.builtInZoomControls = false
        w.isVerticalScrollBarEnabled = false
        w.overScrollMode = View.OVER_SCROLL_NEVER
        w.addJavascriptInterface(Bridge(), "RenacerApp")
        w.webViewClient = object : WebViewClient() {
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    val h = currentHost ?: ""
                    showConnect("No pude conectar con $h.", failedHost = h)
                }
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                if (request.isForMainFrame && response.statusCode == 404) {
                    showConnect("La PC tiene una versión vieja de Renacer LightShow. Instalá la última versión en la PC.", auto = false)
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = false
        }
        w.visibility = View.GONE
        return w
    }

    inner class Bridge {
        @JavascriptInterface
        fun changePc() {
            main.post { showConnect(null, auto = false) }
        }
    }

    private fun open(host: String) {
        currentHost = host
        prefs.edit().putString("host", host).apply()
        hideKeyboard()
        connectBox.visibility = View.GONE
        web.visibility = View.VISIBLE
        web.loadUrl("http://$host/remoto")
    }

    private fun showConnect(message: String?, auto: Boolean = true, failedHost: String? = null) {
        web.stopLoading()
        web.loadUrl("about:blank")
        web.visibility = View.GONE
        connectBox.visibility = View.VISIBLE
        currentHost = null
        status.text = message ?: "Buscando la PC en el Wi-Fi…"
        discover(message, auto, failedHost)
    }

    // ------------------------------------------------------------------ pantalla de conexión

    private fun dp(v: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun bg(color: Int, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        cornerRadius = dp(10).toFloat()
        setColor(color)
        if (stroke != null) setStroke(dp(1), stroke)
    }

    private fun button(text: String, primary: Boolean = false): Button = Button(this).apply {
        this.text = text
        isAllCaps = false
        textSize = 16f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(if (primary) AMBER_INK else TEXT)
        background = if (primary) bg(AMBER) else bg(CTRL)
        stateListAnimator = null
        setPadding(dp(14), dp(14), dp(14), dp(14))
    }

    private fun label(text: String, size: Float, color: Int = TEXT, bold: Boolean = false): TextView = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
    }

    private fun LinearLayout.add(v: View, top: Int = 0) {
        addView(v, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(top) })
    }

    private fun buildConnect(): View {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(36), dp(22), dp(28))
        }
        col.add(label("Renacer", 15f, AMBER, true))
        col.add(label("LightShow Remoto", 28f, TEXT).apply { typeface = Typeface.create(Typeface.SERIF, Typeface.BOLD) })
        status = label("Buscando la PC en el Wi-Fi…", 15f, MUTED)
        col.add(status, 14)

        found = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.add(found, 12)

        searchBtn = button("Buscar de nuevo").apply { setOnClickListener { status.text = "Buscando la PC en el Wi-Fi…"; discover(null, auto = false) } }
        col.add(searchBtn, 10)

        col.add(label("O escribí la dirección que muestra la PC", 14f, MUTED), 30)
        addr = EditText(this).apply {
            hint = "192.168.0.10"
            setHintTextColor(0xFF6E6475.toInt())
            setTextColor(TEXT)
            textSize = 18f
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            imeOptions = EditorInfo.IME_ACTION_GO
            background = bg(PANEL, LINE)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            setOnEditorActionListener { _, id, ev ->
                if (id == EditorInfo.IME_ACTION_GO || ev?.keyCode == KeyEvent.KEYCODE_ENTER) { connectManual(); true } else false
            }
        }
        col.add(addr, 8)
        col.add(button("Conectar", primary = true).apply { setOnClickListener { connectManual() } }, 10)

        col.add(label(
            "Para que funcione:\n" +
                "• La PC y el celular tienen que estar en el mismo Wi-Fi.\n" +
                "• En la PC, en «Show y ajustes», activá «Permitir controlar desde el celular».\n" +
                "• Si Windows pregunta por el firewall, tocá «Permitir».",
            13.5f, MUTED
        ).apply { setLineSpacing(0f, 1.25f) }, 30)

        return ScrollView(this).apply {
            setBackgroundColor(BG)
            isFillViewport = true
            addView(col)
        }
    }

    private fun connectManual() {
        var h = addr.text.toString().trim()
            .removePrefix("http://").removePrefix("https://").trimEnd('/')
            .removeSuffix("/remoto").trimEnd('/')
        if (h.isEmpty()) {
            Toast.makeText(this, "Escribí la dirección de la PC", Toast.LENGTH_SHORT).show()
            return
        }
        if (!h.contains(":")) h = "$h:$DEFAULT_PORT"
        open(h)
    }

    private fun hideKeyboard() {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(addr.windowToken, 0)
    }

    private fun showFound(list: List<Pc>, failMessage: String?) {
        found.removeAllViews()
        searchBtn.isEnabled = true
        if (list.isEmpty()) {
            status.text = (failMessage?.let { "$it\n\n" } ?: "") +
                "No encontré la PC. Revisá que LightShow esté abierto y que el control desde el celular esté activado."
            return
        }
        status.text = (failMessage?.let { "$it\n\n" } ?: "") + if (list.size == 1) "Encontré esta PC:" else "Elegí la PC:"
        for (pc in list) {
            val b = button("${pc.name}\n${pc.show}  ·  ${pc.host}", primary = true).apply {
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                setOnClickListener { open(pc.host) }
            }
            found.addView(b, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
        }
    }

    // ------------------------------------------------------------------ búsqueda por la red

    private fun broadcastTargets(): List<InetAddress> {
        val out = linkedSetOf<InetAddress>()
        try {
            for (ni in NetworkInterface.getNetworkInterfaces()) {
                if (!ni.isUp || ni.isLoopback) continue
                for (ia in ni.interfaceAddresses) {
                    ia.broadcast?.let { out.add(it) }
                }
            }
        } catch (_: Exception) {
        }
        try {
            out.add(InetAddress.getByName("255.255.255.255"))
        } catch (_: Exception) {
        }
        return out.toList()
    }

    private fun discover(failMessage: String?, auto: Boolean, failedHost: String? = null) {
        if (searching) return
        searching = true
        searchBtn.isEnabled = false
        found.removeAllViews()
        Thread {
            val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val lock = wifi.createMulticastLock("renacer")
            val results = linkedMapOf<String, Pc>()
            try {
                lock.setReferenceCounted(false)
                lock.acquire()
                DatagramSocket().use { s ->
                    s.broadcast = true
                    s.soTimeout = 400
                    val ask = ASK.toByteArray()
                    val buf = ByteArray(1024)
                    repeat(4) {
                        for (t in broadcastTargets()) {
                            try {
                                s.send(DatagramPacket(ask, ask.size, t, DISCOVERY_PORT))
                            } catch (_: Exception) {
                            }
                        }
                        val until = System.currentTimeMillis() + 600
                        while (System.currentTimeMillis() < until) {
                            try {
                                val p = DatagramPacket(buf, buf.size)
                                s.receive(p)
                                val j = JSONObject(String(p.data, 0, p.length))
                                val ip = p.address.hostAddress ?: continue
                                val host = "$ip:${j.optInt("port", DEFAULT_PORT)}"
                                results[host] = Pc(
                                    j.optString("pc", "PC"), host,
                                    j.optString("show", ""), j.optString("version", "")
                                )
                            } catch (_: SocketTimeoutException) {
                                break
                            } catch (_: Exception) {
                            }
                        }
                    }
                }
            } catch (_: Exception) {
            } finally {
                try { lock.release() } catch (_: Exception) {}
            }
            main.post {
                searching = false
                if (connectBox.visibility != View.VISIBLE) return@post
                val list = results.values.toList()
                // si hay una sola PC (y no es la que acaba de fallar) entra directo
                if (auto && list.size == 1 && list[0].host != failedHost) {
                    open(list[0].host)
                } else {
                    showFound(list, failMessage)
                }
            }
        }.start()
    }

    // ------------------------------------------------------------------ botón Atrás

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        val now = System.currentTimeMillis()
        if (now - lastBack < 2000) {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        } else {
            lastBack = now
            Toast.makeText(this, "Tocá Atrás otra vez para salir", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}
