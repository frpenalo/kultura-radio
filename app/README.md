# Kultura Radio · App nativa

App movil (iOS + Android) de Kultura Radio, construida con Expo (React Native)
y `expo-audio`. Es el espejo nativo de la PWA (`/opt/subwave/pwa/`) y resuelve
lo que iOS no permite a una web instalada:

- **Lock screen** con la cancion actual, actualizada en vivo
  (`setActiveForLockScreen` + `updateLockScreenMetadata`, modo live stream).
- **Bluetooth del carro**: el sistema maneja los controles remotos; al volver
  la conexion, el carro puede reanudar con el boton de play nativo.
- Audio en segundo plano real (background mode `audio` en iOS, foreground
  service en Android, via el plugin `expo-audio`).

La app NO tiene backend propio: consume los endpoints publicos de
kulturaradio.com (`/stream.mp3`, `/api/now-playing`, `/api/state`,
`/api/request`). Nada del servidor cambia.

## Estructura

- `App.js` — UI completa: 4 pestanas (Radio, Pedir, Programa, Mas), mini
  player, badge EN VIVO, misma paleta y fuentes de la PWA (Fraunces + Outfit).
- `src/player.js` — motor de audio: player unico, conexion fresca por play
  (cache-buster), metadata de lock screen.
- `src/theme.js` — colores y URLs base.

## Desarrollo

`expo-audio` con lock screen requiere build de desarrollo (no sirve Expo Go):

```
npx eas-cli build --profile development --platform android
npx expo start
```

## Builds (EAS, compila en la nube, sin Mac)

- Android APK de prueba: `npx eas-cli build --profile preview --platform android`
- iOS (requiere cuenta Apple Developer $99/ano): `npx eas-cli build --profile production --platform ios`

Primera vez: `npx eas-cli login` y `npx eas-cli init` (crea el proyecto en Expo).

## Nota de licencia

Se descarto `react-native-track-player`: su v5 paso a licencia comercial y la
v4 gratuita no soporta la arquitectura nueva de React Native (Expo SDK 55+).
`expo-audio` es oficial, MIT, y cubre lock screen + live stream.
