// Registro para notificaciones push (avisos de EN VIVO). Se pide permiso en
// el primer play, no al abrir la app. Si el oyente dice que no, la radio
// funciona igual; solo no recibe avisos.
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { Platform } from "react-native";
import { BASE } from "./theme";

// Por defecto Expo TRAGA las notificaciones si la app esta abierta en
// pantalla (verificado en la prueba del 11-oct). Esto las muestra siempre.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

let attempted = false;

export async function registerPush() {
  if (attempted) return;
  attempted = true;
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Kultura Radio",
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
      });
    }
    const perm = await Notifications.requestPermissionsAsync();
    if (!perm.granted) return;
    const projectId =
      Constants.expoConfig && Constants.expoConfig.extra && Constants.expoConfig.extra.eas
        ? Constants.expoConfig.extra.eas.projectId
        : undefined;
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await fetch(BASE + "/api/push/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token }),
    });
  } catch (e) {
    // Sin Firebase configurado o sin red: silencioso; se reintenta en el
    // proximo arranque de la app.
    attempted = false;
  }
}
