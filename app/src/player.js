// Motor de audio NATIVO (expo-audio): audio en segundo plano, lock screen que
// se actualiza siempre y controles remotos (carro, audifonos) manejados por el
// sistema. Reemplaza el MediaSession web que iOS ignoraba en la PWA instalada.
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import { requireOptionalNativeModule } from "expo-modules-core";
import { APP_VER, BASE, STREAM, ARTWORK } from "./theme";

// Modulo nativo propio (modules/kultura-audio): dice si hay llamada, si otra
// app graba o si otra app suena. Sin el (web, simulacion) vale null y la
// logica queda como antes.
const KulturaAudio = requireOptionalNativeModule("KulturaAudio");
function estadoAudio() {
  try { return KulturaAudio ? KulturaAudio.estado() : null; } catch (e) { return null; }
}

// Fuentes de stream desde el servidor: primario (Live365, para que los
// oyentes cuenten en sus reportes y licencias) y respaldo (nuestro VPS). El
// default ya trae las dos: si la config no carga (carro sin senal al abrir),
// igual hay respaldo. Se reintenta leer la config en cada arranque.
let fuentes = ["https://streaming.live365.com/a21141", STREAM];
let fuenteIdx = 0;
let configOk = false;
function leerConfig() {
  if (configOk) return;
  fetch(BASE + "/api/stream-config")
    .then((r) => r.json())
    .then((c) => {
      const l = [];
      if (c && c.primario) l.push(c.primario);
      if (c && c.respaldo && c.respaldo !== c.primario) l.push(c.respaldo);
      if (l.length) { fuentes = l; configOk = true; }
    })
    .catch(() => {});
}
leerConfig();

// "Reporte de vuelo": cada corte, pausa o rescate se avisa al servidor
// (sin datos personales) para diagnosticar con evidencia, no a ciegas.
const sesion = Math.random().toString(36).slice(2, 10);
function reporte(ev, extra) {
  fetch(BASE + "/api/telemetria", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ev, v: APP_VER, s: sesion, f: fuenteIdx % fuentes.length, ...(extra || {}) }),
  }).catch(() => {});
}

// Player unico a nivel de modulo: no se libera al navegar entre pantallas.
export const player = createAudioPlayer(null, { updateInterval: 1000 });

let modeReady = false;
async function ensureMode() {
  if (modeReady) return;
  await setAudioModeAsync({
    playsInSilentMode: true,
    shouldPlayInBackground: true,
    // doNotMix es requisito para que funcionen los controles de lock screen.
    interruptionMode: "doNotMix",
  });
  modeReady = true;
}

function lockMeta(title, artist, art) {
  return {
    title: title || "Kultura Radio",
    artist: artist || "la que nos une",
    albumTitle: "Kultura Radio",
    // Caratula real del album cuando Live365 la trae; la K si no.
    artworkUrl: art || ARTWORK,
  };
}

// Intencion de escucha: la radio quiere sonar hasta que el usuario la pare
// (boton de la app, temporizador o modo grabacion). Lo que la calla sin que
// el oyente lo pida (cortes de red, Live365 cerrando la conexion, Bluetooth
// del carro) se reintenta; ver la logica del listener de abajo.
let wantPlay = false;
let lastMeta = null;
let resumeTimer = null;

let intentos = [];      // auto-reanudaciones tras PAUSA (posible intencion real)
let caidas = [];        // cortes del stream (red / servidor que cierra)
let bufferDesde = 0;    // desde cuando esta atascado cargando
let respaldoDesde = 0;  // desde cuando estamos en la fuente de respaldo
let ultimoArranque = 0; // para no confundir la carga inicial con un corte

// Llamada o grabacion en curso (telefono, WhatsApp, nota de voz): Android
// pausa la radio y la reanuda SOLO al terminar, siempre que no le cambiemos la
// fuente. Reconectar aqui seria peor que inutil: expo-audio suena aunque
// Android le niegue el audio, o sea encima de la llamada. Se espera vigilando
// cada 3 s; si al terminar Android no la reanudo, la reanudamos nosotros.
let enInterrupcion = false;
function interrumpido() {
  const ea = estadoAudio();
  return !!(ea && (ea.llamada || ea.grabando)) && (ea.llamada ? "llamada" : "grabacion");
}
function esperarInterrupcion(motivo) {
  if (!enInterrupcion) { enInterrupcion = true; reporte("interrupcion", { motivo }); }
  if (resumeTimer) clearTimeout(resumeTimer);
  resumeTimer = setTimeout(function revisar() {
    resumeTimer = null;
    if (!wantPlay || player.playing) { enInterrupcion = false; return; }
    if (interrumpido()) { resumeTimer = setTimeout(revisar, 3000); return; }
    resumeTimer = setTimeout(() => {
      resumeTimer = null;
      enInterrupcion = false;
      if (!wantPlay || player.playing) return;
      reporte("fin-interrupcion");
      startStream(lastMeta).catch(() => {});
    }, 3000);
  }, 3000);
}

function cambiarFuente(motivo) {
  fuenteIdx++;
  // Cada fuente tiene que fallar por su cuenta: si los cortes viejos de la
  // otra contaran, un solo corte en el respaldo devolveria a la que fallaba.
  caidas = [];
  respaldoDesde = fuenteIdx % fuentes.length ? Date.now() : 0;
  reporte("cambio-fuente", { motivo });
}

player.addListener("playbackStatusUpdate", (st) => {
  const now = Date.now();
  if (st.playing) {
    // Play desde el lock screen re-arma la intencion.
    wantPlay = true;
    bufferDesde = 0;
    enInterrupcion = false;
    if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null; }
    return;
  }
  if (!wantPlay) return;
  if (st.isBuffering) {
    // Buffering eterno (la red del carro cambiando de WiFi a datos) = app
    // "congelada": a los 20s se reconecta; si ya paso antes, con la otra fuente.
    if (!bufferDesde) bufferDesde = now;
    if (now - bufferDesde > 20000 && !resumeTimer) {
      bufferDesde = 0;
      caidas = caidas.filter((t) => now - t < 120000);
      caidas.push(now);
      reporte("rescate-buffer", { n: caidas.length });
      if (caidas.length >= 2) cambiarFuente("buffer");
      startStream(lastMeta).catch(() => {});
    }
    return;
  }
  bufferDesde = 0;
  if (resumeTimer) return;
  // Un stream en vivo que TERMINA no es una pausa del oyente: es el servidor
  // (Live365) cerrando la conexion o la red cayendo. Eso se reintenta SIEMPRE
  // y nunca cuenta como "el oyente quiere silencio"; si se repite en 2 min,
  // se pasa a la otra fuente. Solo una pausa limpia (fuente cargada, sin
  // terminar) es candidata a intencion real del oyente: el Bluetooth del
  // carro pausa en rafaga, asi que se respeta recien a la 3a en un minuto.
  // Recien arrancado, el reproductor pasa un instante "sin cargar": eso es
  // carga normal, no un corte.
  if (!st.isLoaded && now - ultimoArranque < 6000) return;
  const motivo = interrumpido();
  if (motivo) { esperarInterrupcion(motivo); return; }
  const termino = !!st.didJustFinish || st.playbackState === "ended" || !st.isLoaded;
  // Otra app tomo el audio (YouTube, Spotify): se le cede, no se pelea.
  if (!termino) {
    const ea = estadoAudio();
    if (ea && ea.otraMusica) { reporte("cede-otra-app"); wantPlay = false; return; }
  }
  if (termino) {
    // Se cuenta como corte solo si al vencer la espera SIGUE sin sonar.
    resumeTimer = setTimeout(() => {
      resumeTimer = null;
      if (!wantPlay || player.playing) return;
      const m2 = interrumpido();
      if (m2) { esperarInterrupcion(m2); return; }
      const t = Date.now();
      caidas = caidas.filter((x) => t - x < 120000);
      caidas.push(t);
      reporte("corte", { n: caidas.length, estado: st.playbackState || "" });
      if (caidas.length >= 2) cambiarFuente("cortes");
      startStream(lastMeta).catch(() => {});
    }, caidas.length >= 3 ? 8000 : 2000);
    return;
  }
  intentos = intentos.filter((t) => now - t < 60000);
  if (intentos.length >= 3) {
    reporte("pausa-respetada");
    wantPlay = false; intentos = []; return;
  }
  reporte("pausa", { n: intentos.length + 1 });
  resumeTimer = setTimeout(() => {
    resumeTimer = null;
    if (!wantPlay || player.playing) return;
    const m2 = interrumpido();
    if (m2) { esperarInterrupcion(m2); return; }
    intentos.push(Date.now());
    startStream(lastMeta).catch(() => {});
  }, [2500, 4000, 8000][intentos.length] || 8000);
});

// Al volver la app al frente: si queria sonar y esta muda, reengancha ya
// (salvo en plena llamada: ahi espera la logica de interrupcion).
export function reanudarSiQuiere() {
  if (wantPlay && !player.playing && !interrumpido()) startStream(lastMeta).catch(() => {});
}

export async function startStream(meta) {
  await ensureMode();
  wantPlay = true;
  if (meta) lastMeta = meta;
  ultimoArranque = Date.now();
  leerConfig();
  // Tras 15 min en el respaldo, el proximo arranque vuelve a Live365 (que es
  // donde cuentan los oyentes); si sigue mal, la logica de cortes regresa.
  if (respaldoDesde && Date.now() - respaldoDesde > 15 * 60000) {
    fuenteIdx = 0;
    respaldoDesde = 0;
    caidas = [];
    reporte("vuelta-primario");
  }
  // Conexion fresca cada vez para enganchar el borde EN VIVO del stream
  // (mismo truco que la PWA: cache-buster, nada de buffer viejo).
  player.replace(fuentes[fuenteIdx % fuentes.length] + "?t=" + Date.now());
  player.setActiveForLockScreen(
    true,
    lockMeta(lastMeta && lastMeta.title, lastMeta && lastMeta.artist, lastMeta && lastMeta.art),
    { isLiveStream: true, showSeekBackward: false, showSeekForward: false }
  );
  player.play();
}

export function stopStream() {
  if (wantPlay) reporte("stop");
  wantPlay = false;
  if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null; }
  try {
    player.pause();
    // Soltamos la fuente para no seguir descargando el stream en pausa.
    player.replace(null);
    player.clearLockScreenControls();
  } catch (e) {}
}

// Actualiza titulo/artista en lock screen, CarPlay y Bluetooth del carro.
export function updateNowPlaying(title, artist, art) {
  lastMeta = { title, artist, art };
  try {
    player.updateLockScreenMetadata(lockMeta(title, artist, art));
  } catch (e) {}
}

// ---- Modo grabacion (dedicatorias). iOS exige allowsRecording en la sesion
// de audio; ademas pausamos la radio para que el mic no capture la musica.
let resumeAfterRec = false;

export async function enterRecordMode() {
  resumeAfterRec = !!player.playing;
  stopStream();
  await setAudioModeAsync({
    allowsRecording: true,
    playsInSilentMode: true,
    shouldPlayInBackground: false,
    interruptionMode: "doNotMix",
  });
  modeReady = false;
}

export async function exitRecordMode() {
  await setAudioModeAsync({
    allowsRecording: false,
    playsInSilentMode: true,
    shouldPlayInBackground: true,
    interruptionMode: "doNotMix",
  });
  modeReady = true;
  // La radio vuelve sola si estaba sonando antes de grabar.
  if (resumeAfterRec) {
    resumeAfterRec = false;
    startStream().catch(() => {});
  }
}
