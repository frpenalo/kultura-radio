// Temas CURADOS de Kultura Radio: 4 pieles diseñadas por la casa (nada de
// skins libres: la marca siempre se ve profesional). Cada tema define la
// paleta completa + los degradados del fondo, vinilo y botones.
export const APP_VER = "v19";
export const BASE = "https://kulturaradio.com";
export const STREAM = BASE + "/stream.mp3";
export const ARTWORK = BASE + "/icons/icon-512.png";

export const THEMES = {
  oficial: {
    // IDENTIDAD OFICIAL (oct 2026): navy profundo + degradado de marca
    // rojo #FF1744 -> naranja #FF6B00 -> dorado #FFB800. La K degradada
    // via markGrad (el topbar la pinta con LinearGradient).
    name: "Oficial",
    bg: "#071725", surface: "#0D2033", surface2: "#143049",
    cream: "#F4F7FB", muted: "rgba(244,247,251,0.55)", faint: "rgba(244,247,251,0.10)",
    terra: "#FF6B00", amber: "#FFB800", teal: "#FF1744", red: "#FF1744", dark: "#FFFFFF",
    markGrad: ["#FF1744", "#FF6B00", "#FFB800"],
    gradRadio: ["#12324F", "#0B2138", "#071725"],
    grad: ["#0D2438", "#09192B", "#071725"],
    vinyl: ["#FFB800", "#FF6B00", "#FF1744", "#2A0610"], vinylLabel: "#0D2033",
    playGrad: ["#FF6B00", "#FF1744"],
    micGrad: ["#FF8A2A", "#FF6B00", "#C21333"],
    sendGrad: ["#FFB800", "#FF6B00"],
  },
  noche: {
    name: "Noche",
    bg: "#0A0A0E", surface: "#15151B", surface2: "#1D1D25",
    cream: "#ECECF1", muted: "rgba(236,236,241,0.55)", faint: "rgba(236,236,241,0.10)",
    terra: "#8A7355", amber: "#C9A15A", teal: "#5A8FA3", red: "#E11D2E", dark: "#121008",
    gradRadio: ["#23232E", "#14141B", "#0A0A0E"],
    grad: ["#1B1B23", "#111117", "#0A0A0E"],
    vinyl: ["#C9A15A", "#6E6E7A", "#2E2E38", "#0E0E14"], vinylLabel: "#3C3C48",
    playGrad: ["#E0BC78", "#C9A15A"],
    micGrad: ["#9C8260", "#8A7355", "#5C4C38"],
    sendGrad: ["#E0BC78", "#C9A15A"],
  },
  tropical: {
    // Verdes ORGANICOS de selva (hoja de platano, guayaba) con mango maduro
    // de acento; nada de teal metalico.
    name: "Tropical",
    bg: "#0C1F12", surface: "#142A1A", surface2: "#1D3A24",
    cream: "#F2F7E8", muted: "rgba(242,247,232,0.55)", faint: "rgba(242,247,232,0.10)",
    terra: "#35874A", amber: "#F7A94B", teal: "#6FBF73", red: "#E11D2E", dark: "#102A16",
    gradRadio: ["#2E6B3A", "#16331D", "#0C1F12"],
    grad: ["#244F2D", "#13281A", "#0C1F12"],
    vinyl: ["#F7A94B", "#35874A", "#174D28", "#06160C"], vinylLabel: "#2E6B3A",
    playGrad: ["#FBC46B", "#F7A94B"],
    micGrad: ["#4CAF7D", "#35874A", "#1C5A30"],
    sendGrad: ["#FBC46B", "#F7A94B"],
  },
  navidad: {
    name: "Navidad",
    bg: "#0E1613", surface: "#17241D", surface2: "#203027",
    cream: "#F6EFE3", muted: "rgba(246,239,227,0.55)", faint: "rgba(246,239,227,0.10)",
    terra: "#C0392B", amber: "#E9C46A", teal: "#3A7D5C", red: "#E11D2E", dark: "#1C1206",
    gradRadio: ["#5E1F17", "#2A2018", "#0E1613"],
    grad: ["#431712", "#201C16", "#0E1613"],
    vinyl: ["#E9C46A", "#C0392B", "#5E1F17", "#1C0D0A"], vinylLabel: "#A83226",
    playGrad: ["#F2D48C", "#E9C46A"],
    micGrad: ["#D65A4A", "#C0392B", "#7E241A"],
    sendGrad: ["#F2D48C", "#E9C46A"],
  },
};

// Compatibilidad: C = tema oficial (player.js y otros no dependen del tema
// activo del usuario).
export const C = THEMES.oficial;

// ---------------------------------------------------------------------------
// SKINS REMOTOS: el servidor publica temas extra (paises, fechas especiales)
// en kulturaradio.com/themes.json y la app los suma SIN actualizarse por
// Google Play. Se validan las llaves antes de aceptar uno (un JSON roto no
// puede tumbar los estilos); los temas de la casa quedan de respaldo offline.
// Llaves opcionales de un tema remoto: fondo (imagen de pantalla completa),
// barras (colores del ecualizador), cielo (estrellas + fugaz), markGrad.
// ---------------------------------------------------------------------------
const LLAVES = ["name", "bg", "surface", "surface2", "cream", "muted", "faint",
  "terra", "amber", "teal", "red", "dark", "gradRadio", "grad", "vinyl",
  "vinylLabel", "playGrad", "micGrad", "sendGrad"];

export function registrarTemas(obj) {
  let n = 0;
  for (const [k, t] of Object.entries(obj || {})) {
    if (/^[a-z0-9-]{2,24}$/.test(k) && t && LLAVES.every((ll) => t[ll] != null)) {
      THEMES[k] = t;
      n++;
    }
  }
  return n;
}
