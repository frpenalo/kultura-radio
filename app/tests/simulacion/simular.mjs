// Simulacion del reproductor de Kultura (src/player.js) con reloj falso.
// Cada escenario carga el modulo desde cero y le da secuencias de estados
// como las que produce expo-audio en el telefono (repetidas cada 1s, que es el
// updateInterval real), y verifica la decision: reintentar, cambiar de
// fuente, o respetar la pausa.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const SRC = process.argv[2];
const L365 = "https://streaming.live365.com/a21141";
const PROPIO = "https://kulturaradio.com/stream";

// --- reloj falso -----------------------------------------------------------
let ahora = 1_800_000_000_000;
let timers = [];
let sigId = 1;
const realSetImmediate = setImmediate;
Date.now = () => ahora;
globalThis.setTimeout = (fn, ms) => { const id = sigId++; timers.push({ id, at: ahora + (ms || 0), fn }); return id; };
globalThis.clearTimeout = (id) => { timers = timers.filter((t) => t.id !== id); };
const vaciar = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => realSetImmediate(r)); };
async function avanzar(ms) {
  const fin = ahora + ms;
  while (ahora < fin) {
    ahora = Math.min(fin, ahora + 100);
    const vencidos = timers.filter((t) => t.at <= ahora);
    timers = timers.filter((t) => t.at > ahora);
    for (const t of vencidos) t.fn();
    await vaciar();
  }
}

// --- red falsa -------------------------------------------------------------
let reportes = [];
globalThis.fetch = async (url, opts) => {
  if (String(url).includes("/api/stream-config")) {
    return { json: async () => ({ primario: L365, respaldo: PROPIO }) };
  }
  if (String(url).includes("/api/telemetria")) {
    reportes.push(JSON.parse(opts.body));
    return { json: async () => ({}) };
  }
  throw new Error("sin red: " + url);
};

// --- modulo bajo prueba (imports redirigidos al doble) ----------------------
fs.copyFileSync(path.join(SRC, "theme.js"), path.join(AQUI, "theme.mjs"));
const codigo = fs.readFileSync(path.join(SRC, "player.js"), "utf8")
  .replace('from "expo-audio"', 'from "./expo-audio-mock.mjs"')
  .replace('from "expo-modules-core"', 'from "./expo-modules-core-mock.mjs"')
  .replace('from "./theme"', 'from "./theme.mjs"');
fs.writeFileSync(path.join(AQUI, "player-bajo-prueba.mjs"), codigo);
const mock = await import(pathToFileURL(path.join(AQUI, "expo-audio-mock.mjs")).href);
const nativo = await import(pathToFileURL(path.join(AQUI, "expo-modules-core-mock.mjs")).href);
const N = nativo.estadoNativo;

let n = 0;
async function cargar() {
  // listeners y registro limpios; modulo nuevo (estado interno desde cero)
  const l = mock.registro;
  l.replaces.length = 0; l.plays = 0; l.pauses = 0;
  N.llamada = false; N.grabando = false; N.otraMusica = false;
  reportes = []; timers = [];
  const m = await import(pathToFileURL(path.join(AQUI, "player-bajo-prueba.mjs")).href + "?n=" + n++);
  await vaciar();
  return m;
}
const fuenteActual = () => (mock.registro.replaces.at(-1) || "").split("?")[0];
const arranques = () => mock.registro.replaces.length;
async function durante(m, seg, st) {
  for (let i = 0; i < seg; i++) { mock.emitir(m.player, st); await avanzar(1000); }
}
const SONANDO = { playing: true, isLoaded: true };
const PAUSA = { playing: false, isLoaded: true, isBuffering: false, didJustFinish: false, playbackState: "paused" };
const FIN = { playing: false, isLoaded: true, isBuffering: false, didJustFinish: true, playbackState: "ended" };
const CAIDO = { playing: false, isLoaded: false, isBuffering: false, playbackState: "idle" };
const CARGANDO = { playing: false, isLoaded: true, isBuffering: true };

const resultados = [];
function chequear(nombre, ok, detalle) { resultados.push({ nombre, ok, detalle }); }

// A: arranque normal (carga inicial no cuenta como corte)
{
  const m = await cargar();
  await m.startStream({ title: "x" });
  await durante(m, 3, { playing: false, isLoaded: false, isBuffering: false });
  await durante(m, 5, SONANDO);
  chequear("A. Arranque normal: la carga inicial no se cuenta como corte",
    arranques() === 1 && !reportes.some((r) => r.ev === "corte") && fuenteActual() === L365,
    `arranques=${arranques()} fuente=${fuenteActual()} reportes=${reportes.map((r) => r.ev)}`);
}

// B: Live365 corta UNA vez -> reconecta a Live365
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  await durante(m, 3, FIN);
  await durante(m, 5, SONANDO);
  chequear("B. Un corte de Live365: reconecta solo, sigue en Live365",
    arranques() === 2 && fuenteActual() === L365,
    `arranques=${arranques()} fuente=${fuenteActual()}`);
}

// C: Live365 corta varias veces seguidas -> pasa al respaldo y NUNCA se rinde
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  for (let i = 0; i < 6; i++) { await durante(m, 10, FIN); await durante(m, 4, SONANDO); }
  const cambios = reportes.filter((r) => r.ev === "cambio-fuente").length;
  chequear("C. Cortes repetidos: cambia de fuente y nunca se rinde",
    cambios >= 1 && !reportes.some((r) => r.ev === "pausa-respetada") && arranques() >= 7,
    `arranques=${arranques()} cambios_fuente=${cambios} fuente_final=${fuenteActual()}`);
}

// D: Bluetooth del carro pausa en rafaga (2 pausas) -> sigue sonando
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  await durante(m, 3, PAUSA); await durante(m, 2, SONANDO);
  await durante(m, 5, PAUSA); await durante(m, 10, SONANDO);
  chequear("D. Rafaga del Bluetooth (2 pausas): se reanuda sola",
    arranques() === 3 && !reportes.some((r) => r.ev === "pausa-respetada"),
    `arranques=${arranques()} reportes=${reportes.map((r) => r.ev)}`);
}

// E: pausa REAL del oyente (insiste) -> se respeta y no pelea
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  for (let i = 0; i < 4; i++) { await durante(m, 9, PAUSA); await durante(m, 1, SONANDO); }
  await durante(m, 30, PAUSA);
  const antes = arranques();
  await durante(m, 30, PAUSA);
  chequear("E. Pausa real que insiste: se respeta (deja de reanudar)",
    reportes.some((r) => r.ev === "pausa-respetada") && arranques() === antes,
    `arranques=${arranques()} respetada=${reportes.some((r) => r.ev === "pausa-respetada")}`);
}

// F: buffering eterno (cambio WiFi -> datos) -> rescate a los 20s
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  await durante(m, 25, CARGANDO);
  chequear("F. App congelada cargando: se rescata sola a los ~20s",
    arranques() === 2 && reportes.some((r) => r.ev === "rescate-buffer"),
    `arranques=${arranques()}`);
}

// G: red caida (fuente no carga) -> reintenta sin rendirse
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  await durante(m, 60, CAIDO);
  chequear("G. Sin red un minuto: sigue reintentando, nunca se rinde",
    arranques() >= 3 && !reportes.some((r) => r.ev === "pausa-respetada"),
    `arranques=${arranques()} fuentes_probadas=${[...new Set(mock.registro.replaces.map((u) => u.split("?")[0]))].length}`);
}

// H: en respaldo mas de 15 min -> el proximo arranque vuelve a Live365
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 5, SONANDO);
  for (let i = 0; i < 3; i++) { await durante(m, 10, FIN); await durante(m, 3, SONANDO); }
  const enRespaldo = fuenteActual() === PROPIO;
  await durante(m, 16 * 60, SONANDO);
  await durante(m, 4, FIN); await durante(m, 3, SONANDO);
  chequear("H. Tras 15 min en respaldo, vuelve a Live365",
    enRespaldo && fuenteActual() === L365 && reportes.some((r) => r.ev === "vuelta-primario"),
    `estuvo_en_respaldo=${enRespaldo} fuente_final=${fuenteActual()} reportes=${reportes.map((r) => r.ev + (r.f!==undefined?'@'+r.f:'')).join(',')}`);
}

// I: el oyente apaga con el boton -> silencio, cero reintentos
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 5, SONANDO);
  m.stopStream();
  const antes = arranques();
  await durante(m, 30, PAUSA);
  chequear("I. Apagar con el boton: se queda apagada",
    arranques() === antes, `arranques_extra=${arranques() - antes}`);
}

// J: llamada de 2 min: Android pausa; la app NO debe reconectar durante la
// llamada (sonaria encima); al colgar Android la reanuda sola.
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  N.llamada = true;
  await durante(m, 120, PAUSA);
  const durante_llamada = arranques();
  N.llamada = false;
  await durante(m, 1, PAUSA);
  await durante(m, 10, SONANDO);
  chequear("J. Llamada de 2 min: no reconecta durante la llamada; al colgar sigue",
    durante_llamada === 1 && arranques() === 1 && reportes.some((r) => r.ev === "interrupcion"),
    `arranques_durante=${durante_llamada} final=${arranques()} reportes=${[...new Set(reportes.map((r) => r.ev))]}`);
}

// K: la llamada termina pero Android no reanuda: la app la reanuda sola
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  N.llamada = true;
  await durante(m, 60, PAUSA);
  N.llamada = false;
  let seg = 0;
  while (arranques() === 1 && seg < 15) { await durante(m, 1, PAUSA); seg++; }
  await durante(m, 10, SONANDO);
  chequear("K. Al colgar sin reanudacion de Android: la app reanuda en segundos",
    arranques() === 2 && seg <= 8 && reportes.some((r) => r.ev === "fin-interrupcion"),
    `arranques=${arranques()} reanudo_a_los=${seg}s reportes=${[...new Set(reportes.map((r) => r.ev))]}`);
}

// L: nota de voz en WhatsApp (otra app grabando): espera callada
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  N.grabando = true;
  await durante(m, 40, PAUSA);
  chequear("L. Grabando nota de voz: la radio no suena encima",
    arranques() === 1, `arranques=${arranques()}`);
}

// M: el oyente abre YouTube/Spotify: la radio cede, no pelea
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  N.otraMusica = true;
  await durante(m, 60, PAUSA);
  chequear("M. Otra app sonando: la radio cede y no pelea el audio",
    arranques() === 1 && reportes.some((r) => r.ev === "cede-otra-app"),
    `arranques=${arranques()}`);
}

// N: llamada que empieza durante un corte de Live365: no reconecta en plena llamada
{
  const m = await cargar();
  await m.startStream({}); await durante(m, 10, SONANDO);
  await durante(m, 1, FIN);
  N.llamada = true;
  await durante(m, 30, FIN);
  chequear("N. Corte de Live365 + llamada: espera a que termine la llamada",
    arranques() === 1, `arranques=${arranques()}`);
}

let fallos = 0;
for (const r of resultados) {
  console.log((r.ok ? "PASA " : "FALLA") + "  " + r.nombre + (r.ok ? "" : "\n        -> " + r.detalle));
  if (!r.ok) fallos++;
}
console.log("\n" + (resultados.length - fallos) + "/" + resultados.length + " escenarios pasan");
process.exit(fallos ? 1 : 0);
