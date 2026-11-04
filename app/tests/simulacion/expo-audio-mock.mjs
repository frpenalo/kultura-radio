// Doble de expo-audio para simular el reproductor sin telefono. Cada player
// tiene SUS listeners (cada escenario carga un modulo nuevo con su player).
export const registro = { replaces: [], plays: 0, pauses: 0 };

export function createAudioPlayer() {
  return {
    playing: false,
    _listeners: [],
    addListener(ev, fn) { if (ev === "playbackStatusUpdate") this._listeners.push(fn); return { remove() {} }; },
    replace(src) { registro.replaces.push(src); this.playing = false; },
    play() { registro.plays++; },
    pause() { registro.pauses++; this.playing = false; },
    setActiveForLockScreen() {},
    updateLockScreenMetadata() {},
    clearLockScreenControls() {},
  };
}

export async function setAudioModeAsync() {}

export function emitir(player, st) {
  player.playing = !!st.playing;
  for (const fn of player._listeners) fn(st);
}
