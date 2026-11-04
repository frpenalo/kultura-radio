// Doble de expo-modules-core: el modulo nativo KulturaAudio con un estado
// que cada escenario controla (llamada, grabacion, otra app sonando).
export const estadoNativo = { llamada: false, grabando: false, otraMusica: false };
export function requireOptionalNativeModule(nombre) {
  if (nombre !== "KulturaAudio") return null;
  return { estado: () => ({ ...estadoNativo }) };
}
