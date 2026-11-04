package expo.modules.kulturaaudio

import android.content.Context
import android.media.AudioManager
import android.os.Build
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

// Estado del audio de Android que JavaScript no puede ver: si hay una llamada
// (telefono o VoIP como WhatsApp), si otra app esta grabando (p. ej. una nota
// de voz) o si otra app esta sonando. AudioManager lo expone sin permisos
// (no hace falta READ_PHONE_STATE).
class KulturaAudioModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("KulturaAudio")

    Function("estado") {
      val am = appContext.reactContext?.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        ?: return@Function mapOf("llamada" to false, "grabando" to false, "otraMusica" to false)
      val modo = am.mode
      val llamada = modo == AudioManager.MODE_RINGTONE ||
        modo == AudioManager.MODE_IN_CALL ||
        modo == AudioManager.MODE_IN_COMMUNICATION ||
        (Build.VERSION.SDK_INT >= 30 && modo == AudioManager.MODE_CALL_SCREENING)
      val grabando = am.activeRecordingConfigurations.isNotEmpty()
      mapOf("llamada" to llamada, "grabando" to grabando, "otraMusica" to am.isMusicActive)
    }
  }
}
