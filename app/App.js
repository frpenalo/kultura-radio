// Kultura Radio - app nativa (Expo + expo-audio).
// V2 visual + TEMAS CURADOS (oct 2026): 4 pieles de la casa (Clasico, Noche,
// Tropical, Navidad) seleccionables en Mas y persistidas. Todo el color de la
// app sale del tema activo via ThemeCtx; los estilos se reconstruyen por tema.
import React, { useEffect, useRef, useState, useCallback, useContext, useMemo, createContext } from "react";
import {
  Alert,
  Animated,
  AppState,
  Dimensions,
  Easing,
  Image,
  Linking,
  Pressable,
  ScrollView,
  Share,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import {
  AudioModule,
  RecordingPresets,
  createAudioPlayer,
  useAudioPlayerStatus,
  useAudioRecorder,
} from "expo-audio";
import * as FileSystem from "expo-file-system/legacy";
import { LinearGradient } from "expo-linear-gradient";
import Svg, { Circle, Defs, Path, RadialGradient, Rect, Stop } from "react-native-svg";
import {
  useFonts,
  Fraunces_600SemiBold,
  Fraunces_700Bold,
} from "@expo-google-fonts/fraunces";
import {
  Outfit_400Regular,
  Outfit_500Medium,
  Outfit_600SemiBold,
} from "@expo-google-fonts/outfit";
import { BebasNeue_400Regular } from "@expo-google-fonts/bebas-neue";
import { APP_VER, BASE, THEMES, registrarTemas } from "./src/theme";
import {
  enterRecordMode,
  exitRecordMode,
  player,
  reanudarSiQuiere,
  startStream,
  stopStream,
  updateNowPlaying,
} from "./src/player";
import { registerPush } from "./src/push";

const PERIODS = { morning: "Mañana", afternoon: "Tarde", evening: "Noche", night: "Noche", late: "Madrugada" };
const REQ_COOLDOWN_MS = 15 * 60 * 1000;
const SLEEP_STEPS = [0, 15, 30, 60];

const ThemeCtx = createContext(null);
const useTheme = () => useContext(ThemeCtx);

// ============================================================================
// AMBIENTE POR TEMA: cada piel trae su atmosfera animada, no solo colores.
// Todas las particulas usan el native driver y viven DETRAS del contenido.
// ============================================================================

// Particula que viaja verticalmente en loop (nieve hacia abajo, chispa hacia
// arriba) con deriva lateral y fade en los extremos.
function Particle({ x, size, dur, delay, drift, color, up, maxOpacity }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(v, { toValue: 1, duration: dur, easing: Easing.linear, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: 0, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [v, dur, delay]);
  const H = Dimensions.get("window").height;
  const translateY = v.interpolate({ inputRange: [0, 1], outputRange: up ? [H + 20, -40] : [-40, H + 20] });
  const translateX = v.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, drift, 0] });
  const opacity = v.interpolate({ inputRange: [0, 0.08, 0.85, 1], outputRange: [0, maxOpacity, maxOpacity, 0] });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", left: x, top: 0, width: size, height: size,
        borderRadius: size / 2, backgroundColor: color, opacity,
        transform: [{ translateY }, { translateX }],
      }}
    />
  );
}

function fieldFor(n, maker) {
  return Array.from({ length: n }, (_, i) => maker(i));
}

function Snow() {
  const flakes = useMemo(() => fieldFor(16, (i) => ({
    x: (Math.random() * 96 + 2) + "%", size: 3 + Math.random() * 4.5,
    dur: 7000 + Math.random() * 7000, delay: Math.random() * 7000,
    drift: (Math.random() - 0.5) * 70,
  })), []);
  return flakes.map((f, i) => (
    <Particle key={i} {...f} color="#FFFFFF" up={false} maxOpacity={0.75} />
  ));
}

function Embers() {
  const sparks = useMemo(() => fieldFor(9, () => ({
    x: (Math.random() * 94 + 3) + "%", size: 2.5 + Math.random() * 3,
    dur: 9000 + Math.random() * 8000, delay: Math.random() * 9000,
    drift: (Math.random() - 0.5) * 50,
  })), []);
  return sparks.map((f, i) => (
    <Particle key={i} {...f} color="#E9A93C" up={true} maxOpacity={0.45} />
  ));
}

// Estrella fija que titila (opacidad en loop con fase propia).
function TwinkleStar({ x, y, size, dur, delay, gold }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(v, { toValue: 1, duration: dur, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: dur, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [v, dur, delay]);
  const opacity = v.interpolate({ inputRange: [0, 1], outputRange: [0.12, 0.9] });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", left: x, top: y, width: size, height: size,
        borderRadius: size / 2, backgroundColor: gold ? "#C9A15A" : "#ECECF1", opacity,
      }}
    />
  );
}

function Stars() {
  const stars = useMemo(() => fieldFor(26, (i) => ({
    x: (Math.random() * 96 + 2) + "%", y: (Math.random() * 55 + 2) + "%",
    size: 1.5 + Math.random() * 2.2, dur: 900 + Math.random() * 1800,
    delay: Math.random() * 3000, gold: i % 4 === 0,
  })), []);
  return stars.map((st, i) => <TwinkleStar key={i} {...st} />);
}

// Fugaz ocasional: un trazo fino con cola cruza el cielo en diagonal y se
// apaga; espera larga al azar entre pasadas para que siga siendo un detalle
// raro y no un show de laser. Cada pase sale de un punto distinto.
function Fugaz() {
  const W = Dimensions.get("window").width;
  const v = useRef(new Animated.Value(0)).current;
  const [pase, setPase] = useState(0);
  const inicio = useMemo(() => ({
    x: Math.random() * W * 0.5 + W * 0.1,
    y: Math.random() * 100 + 24,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [pase]);
  useEffect(() => {
    v.setValue(0);
    const seq = Animated.sequence([
      Animated.delay(18000 + Math.random() * 32000),
      Animated.timing(v, { toValue: 1, duration: 680, easing: Easing.out(Easing.quad), useNativeDriver: true }),
    ]);
    seq.start(({ finished }) => { if (finished) setPase((p) => p + 1); });
    return () => seq.stop();
  }, [v, pase]);
  const tx = v.interpolate({ inputRange: [0, 1], outputRange: [0, 170] });
  const ty = v.interpolate({ inputRange: [0, 1], outputRange: [0, 110] });
  const opacity = v.interpolate({ inputRange: [0, 0.12, 0.75, 1], outputRange: [0, 0.9, 0.45, 0] });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", left: inicio.x, top: inicio.y, width: 64, height: 1.6,
        opacity, transform: [{ translateX: tx }, { translateY: ty }, { rotate: "33deg" }],
      }}
    >
      <LinearGradient
        colors={["rgba(236,236,241,0)", "#FFFFFF"]}
        start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
        style={{ flex: 1, borderRadius: 1 }}
      />
    </Animated.View>
  );
}

// Follaje tropical: columnas de hojas anchas (tipo platano) que SUBEN por los
// lados hasta arriba, en silueta negro-fade con capas de profundidad, y
// mangos colgando tenues entre las hojas bajas.
function Leaf({ w, color }) {
  const h = Math.round(w * 0.38);
  // Hoja-lente: ancha al centro, punta suave (nada de patas de arana).
  return (
    <Svg width={w} height={h} viewBox="0 0 120 46">
      <Path d="M4 23 C28 5 88 0 114 15 C118 18 118 28 114 31 C88 46 28 41 4 23 Z" fill={color} />
      <Path d="M8 23 L110 23" stroke="rgba(255,255,255,0.07)" strokeWidth="2" fill="none" />
    </Svg>
  );
}

function Mango({ size }) {
  return (
    <Svg width={size} height={size * 1.3} viewBox="0 0 20 26">
      <Path d="M10 3 C10 1 11 0 12 1" stroke="#05100C" strokeWidth="2" fill="none" />
      <Path d="M10 3 C4 4 1 10 2 16 C3 22 8 25 11 25 C16 25 19 20 18 13 C17 7 14 3 10 3 Z" fill="#F7A94B" />
    </Svg>
  );
}

function FoliageSide({ side }) {
  const H = Dimensions.get("window").height;
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: side === "left" ? 5600 : 6400, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: side === "left" ? 5600 : 6400, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [v, side]);
  const rotate = v.interpolate({ inputRange: [0, 1], outputRange: ["-1.2deg", "1.2deg"] });
  // Hojas de arriba a abajo: angulo, tamano, altura (fraccion de pantalla),
  // color y opacidad varian para que se sienta follaje vivo, no estampado.
  const leaves = [
    // DOSEL: hojas largas arriba que caen arqueadas hacia el centro, por
    // detras del vinilo (el follaje vive bajo el contenido).
    { top: -0.01, ang: 62, w: 225, c: "#05100C", o: 0.46 },
    { top: 0.05, ang: 50, w: 205, c: "#123A1C", o: 0.32 },
    { top: 0.13, ang: 40, w: 185, c: "#05100C", o: 0.44 },
    { top: 0.24, ang: 56, w: 160, c: "#17451F", o: 0.26 },
    // flanco medio
    { top: 0.38, ang: 34, w: 170, c: "#05100C", o: 0.44 },
    { top: 0.52, ang: 60, w: 165, c: "#123A1C", o: 0.3 },
    // base frondosa
    { top: 0.65, ang: 42, w: 200, c: "#05100C", o: 0.5 },
    { top: 0.77, ang: 66, w: 185, c: "#17451F", o: 0.3 },
    { top: 0.86, ang: 50, w: 215, c: "#05100C", o: 0.52 },
  ];
  const mangos = [
    { top: 0.6, off: 46, size: 15, o: 0.3 },
    { top: 0.72, off: 70, size: 19, o: 0.34 },
    { top: 0.81, off: 38, size: 13, o: 0.26 },
  ];
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", top: 0, bottom: 0, width: 150,
        [side]: 0, transform: [{ rotate }],
      }}
    >
      {leaves.map((L, i) => (
        <View
          key={i}
          style={{
            position: "absolute", top: L.top * H, [side]: -L.w * 0.42, opacity: L.o,
            transform: [{ rotate: (side === "left" ? 1 : -1) * L.ang + "deg" }, ...(side === "right" ? [{ scaleX: -1 }] : [])],
          }}
        >
          <Leaf w={L.w} color={L.c} />
        </View>
      ))}
      {mangos.map((m, i) => (
        <View key={"m" + i} style={{ position: "absolute", top: m.top * H, [side]: m.off, opacity: m.o }}>
          <Mango size={m.size} />
        </View>
      ))}
    </Animated.View>
  );
}

function Palms() {
  return (
    <>
      <FoliageSide side="left" />
      <FoliageSide side="right" />
    </>
  );
}

// Guirnalda de luces navidenas: cable con dos pandeos y bombillos de colores
// que titilan a destiempo, colgada bajo la barra superior.
const LIGHT_COLORS = ["#E25555", "#E9C46A", "#3A9D6C", "#5A8FA3"];
function Bulb({ xFrac, y, color, delay, dur }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(v, { toValue: 1, duration: dur, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: dur, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [v, delay, dur]);
  const opacity = v.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] });
  return (
    <Animated.View
      style={{
        position: "absolute", left: xFrac, top: y, width: 9, height: 9,
        borderRadius: 5, backgroundColor: color, opacity,
        shadowColor: color, shadowOpacity: 0.9, shadowRadius: 6, elevation: 4,
      }}
    />
  );
}

function ChristmasLights() {
  const W = Dimensions.get("window").width;
  // y de cada bombillo sigue el pandeo del cable (dos curvas)
  const ys = [12, 22, 29, 24, 14, 13, 23, 30, 25, 15, 12];
  const bulbs = useMemo(() => ys.map((y, i) => ({
    xFrac: ((i + 0.5) / ys.length) * 100 + "%", y: y + 8,
    color: LIGHT_COLORS[i % LIGHT_COLORS.length],
    delay: (i * 137) % 900, dur: 650 + ((i * 97) % 500),
  })), []);
  return (
    <View pointerEvents="none" style={{ height: 52 }}>
      <Svg width={W} height={40} viewBox={`0 0 ${W} 40`}>
        <Path
          d={`M0 10 Q ${W * 0.25} 34 ${W * 0.5} 16 Q ${W * 0.75} 36 ${W} 12`}
          stroke="rgba(246,239,227,0.35)" strokeWidth="2" fill="none"
        />
      </Svg>
      {bulbs.map((b, i) => <Bulb key={i} {...b} />)}
    </View>
  );
}

function Ambient({ themeKey, cielo, lightsTop }) {
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {themeKey === "navidad" && <Snow />}
      {themeKey === "navidad" && (
        <View style={{ position: "absolute", top: lightsTop, left: 0, right: 0 }}>
          <ChristmasLights />
        </View>
      )}
      {(themeKey === "noche" || cielo) && <Stars />}
      {(themeKey === "noche" || cielo) && <Fugaz />}
      {/* tropical: la foto manda sola; el follaje animado se retiro (30-oct) */}
      {themeKey === "oficial" && <Embers />}
    </View>
  );
}

// ---- Vinilo: con caratula del album como cara del disco (surcos y hoyito
// encima para que siga siendo un vinilo); sin caratula, el gradiente del tema.
function VinylOverlay() {
  const { T } = useTheme();
  const grooves = [];
  for (let r = 30; r <= 96; r += 7) {
    grooves.push(<Circle key={r} cx="104" cy="104" r={r} stroke="rgba(10,8,6,0.22)" strokeWidth="1.5" fill="none" />);
  }
  return (
    <Svg width={208} height={208} viewBox="0 0 208 208" style={StyleSheet.absoluteFill}>
      {grooves}
      <Circle cx="104" cy="104" r="102" stroke="rgba(0,0,0,0.45)" strokeWidth="4" fill="none" />
      <Circle cx="104" cy="104" r="11" fill={T.bg} stroke="rgba(255,255,255,0.35)" strokeWidth="3" />
    </Svg>
  );
}

function Vinyl() {
  const { T } = useTheme();
  const grooves = [];
  for (let r = 22; r <= 96; r += 7) {
    grooves.push(<Circle key={r} cx="104" cy="104" r={r} stroke="rgba(10,8,6,0.25)" strokeWidth="1.5" fill="none" />);
  }
  return (
    <Svg width={208} height={208} viewBox="0 0 208 208">
      <Defs>
        <RadialGradient id="vg" cx="35%" cy="30%" r="85%">
          <Stop offset="0%" stopColor={T.vinyl[0]} />
          <Stop offset="34%" stopColor={T.vinyl[1]} />
          <Stop offset="68%" stopColor={T.vinyl[2]} />
          <Stop offset="100%" stopColor={T.vinyl[3]} />
        </RadialGradient>
      </Defs>
      <Circle cx="104" cy="104" r="103" fill="url(#vg)" />
      {grooves}
      {/* marcas fuera de centro: sin ellas un circulo girando se ve quieto */}
      <Rect x="101" y="30" width="6" height="26" rx="3" fill="rgba(255,255,255,0.35)" />
      <Circle cx="104" cy="66" r="4.5" fill="rgba(255,255,255,0.4)" />
      <Circle cx="104" cy="104" r="30" fill={T.vinylLabel} stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" />
      <Circle cx="104" cy="104" r="11" fill={T.bg} stroke="rgba(255,255,255,0.25)" strokeWidth="3" />
    </Svg>
  );
}

// ---- Vinilo girando: el loop vive DENTRO del componente (valor y animacion
// nacen con cada montaje). Si viviera arriba, cualquier reconstruccion de la
// pantalla (cambio de tema, de pestana) deja la animacion nativa huerfana y
// el disco se congela.
function SpinningVinyl({ playing, art }) {
  const spin = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (playing) {
      const loop = Animated.loop(
        Animated.timing(spin, { toValue: 1, duration: 7000, easing: Easing.linear, useNativeDriver: true })
      );
      loop.start();
      return () => loop.stop();
    }
  }, [playing, spin]);
  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  return (
    <Animated.View style={{ transform: [{ rotate }] }}>
      {art ? (
        <View style={{ width: 208, height: 208 }}>
          {/* El redondeo va en la IMAGEN misma: el clip del contenedor falla
              en Android sobre vistas rotando y dejaba la foto cuadrada. */}
          <Image source={{ uri: art }} style={{ width: 208, height: 208, borderRadius: 104 }} />
          <VinylOverlay />
        </View>
      ) : (
        <Vinyl />
      )}
    </Animated.View>
  );
}

// ---- Bracito del tocadiscos: en reposo descansa afuera; al sonar la radio
// gira sobre su pivote y aterriza en los surcos (con un rebotico analogico).
function ToneArm({ playing }) {
  const { T } = useTheme();
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(v, {
      toValue: playing ? 1 : 0,
      duration: playing ? 900 : 550,
      easing: playing ? Easing.out(Easing.back(1.5)) : Easing.inOut(Easing.quad),
      useNativeDriver: true,
    }).start();
  }, [playing, v]);
  const rotate = v.interpolate({ inputRange: [0, 1], outputRange: ["-32deg", "7deg"] });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", top: -10, right: -18, zIndex: 5,
        transform: [{ translateY: -76 }, { rotate }, { translateY: 76 }],
      }}
    >
      <Svg width={84} height={192} viewBox="0 0 84 192">
        <Circle cx="42" cy="22" r="16" fill={T.surface2} stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
        <Circle cx="42" cy="22" r="6" fill="#D9CFC0" />
        <Rect x="34" y="1" width="16" height="12" rx="4" fill="#8C8073" />
        <Rect x="38.5" y="22" width="7" height="114" rx="3.5" fill="#D9CFC0" />
        <Rect x="31" y="134" width="22" height="34" rx="6" fill={T.surface2} stroke="#D9CFC0" strokeWidth="1.5" />
        <Rect x="39" y="166" width="6" height="12" rx="2" fill={T.amber} />
      </Svg>
    </Animated.View>
  );
}

// ---- Anillo de halo que pulsa (se usa en el disco y en el mic de dedicar).
function PulseRing({ size, color, delay, border }) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(v, { toValue: 1, duration: 2600, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: 0, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [v, delay]);
  const scale = v.interpolate({ inputRange: [0, 1], outputRange: [0.84, 1.18] });
  const opacity = v.interpolate({ inputRange: [0, 0.25, 1], outputRange: [0, 0.7, 0] });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        position: "absolute", width: size, height: size, borderRadius: size / 2,
        borderWidth: border || 1.5, borderColor: color, opacity, transform: [{ scale }],
      }}
    />
  );
}

// ---- Barra de la onda de audio: baila solo cuando la radio suena.
function WaveBar({ seed, playing, color }) {
  const { s } = useTheme();
  const v = useRef(new Animated.Value(0.25)).current;
  useEffect(() => {
    if (playing) {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.delay((seed * 97) % 420),
          Animated.timing(v, { toValue: 0.35 + ((seed * 53) % 60) / 100, duration: 380 + ((seed * 31) % 260), useNativeDriver: true }),
          Animated.timing(v, { toValue: 0.18 + ((seed * 29) % 20) / 100, duration: 420 + ((seed * 17) % 220), useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    Animated.timing(v, { toValue: 0.22, duration: 300, useNativeDriver: true }).start();
  }, [playing, seed, v]);
  return <Animated.View style={[s.waveBar, color && { backgroundColor: color }, { transform: [{ scaleY: v }] }]} />;
}

function Root() {
  const { T, s, themeKey, setThemeKey } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState("radio");
  const [np, setNp] = useState({ title: "Kultura Radio", artist: "la que nos une", live: false, album: "", art: null });
  const [ctx, setCtx] = useState({});
  const [online, setOnline] = useState(null);
  const [upcoming, setUpcoming] = useState(null);
  const [prog, setProg] = useState(null);
  const [sleepIdx, setSleepIdx] = useState(0);

  const status = useAudioPlayerStatus(player);
  const playing = !!(status && (status.playing || status.isBuffering));
  const npRef = useRef(np);
  npRef.current = np;
  const playingRef = useRef(playing);
  playingRef.current = playing;

  // ---- Ahora suena. OJO: React Native PAUSA setInterval en segundo plano
  // (Android); la lock screen se alimenta del heartbeat de playbackStatusUpdate
  // de abajo, que es nativo y sigue latiendo mientras suena el audio.
  const lastPollRef = useRef(0);
  const poll = useCallback(() => {
    lastPollRef.current = Date.now();
    fetch(BASE + "/api/now-playing?t=" + Date.now(), { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        const n = (d && d.nowPlaying) || {};
        const c = (d && d.context) || {};
        const next = {
          title: n.title || "Kultura Radio",
          artist: n.artist || "la que nos une",
          live: !!n.live,
          album: n.album || "",
          art: n.art || null,
        };
        setNp(next);
        setCtx(c);
        setOnline(true);
        if (playingRef.current) updateNowPlaying(next.title, next.artist, next.art);
      })
      .catch(() => setOnline(false));
  }, []);
  useEffect(() => {
    poll();
    const id = setInterval(poll, 15000);
    const beat = player.addListener("playbackStatusUpdate", () => {
      if (Date.now() - lastPollRef.current > 12000) poll();
    });
    const app = AppState.addEventListener("change", (st) => {
      if (st === "active") { poll(); reanudarSiQuiere(); }
    });
    return () => {
      clearInterval(id);
      beat.remove();
      app.remove();
    };
  }, [poll]);

  // Geo: la licencia (Live365) cubre US/CA/UK/MX; fuera de ahi no se reproduce.
  const geoOkRef = useRef(true);
  useEffect(() => {
    fetch(BASE + "/api/geo")
      .then((r) => r.json())
      .then((g) => {
        if (g && g.permitido === false) {
          geoOkRef.current = false;
          // Si el encendido automatico le gano a esta respuesta, se apaga.
          stopStream();
        }
      })
      .catch(() => {});
  }, []);
  const geoBloqueado = useCallback(() => {
    if (geoOkRef.current) return false;
    Alert.alert(
      "Fuera de cobertura",
      "Kultura Radio solo está disponible en Estados Unidos, Canadá, Reino Unido y México por licencias de música."
    );
    return true;
  }, []);

  const toggle = useCallback(() => {
    if (playingRef.current) stopStream();
    else {
      if (geoBloqueado()) return;
      startStream(npRef.current).then(poll).catch(() => {});
      registerPush();
    }
  }, [poll, geoBloqueado]);

  // ---- Encendido de tocadiscos: al abrir la app, el bracito baja y la radio
  // arranca sola. El permiso de push se pide a los 30s de escucha (no en la
  // entrada, que espanta).
  useEffect(() => {
    const t = setTimeout(() => {
      if (!geoOkRef.current) return;
      startStream(npRef.current).then(poll).catch(() => {});
    }, 700);
    const p = setTimeout(() => registerPush(), 30000);
    return () => { clearTimeout(t); clearTimeout(p); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Modo reposo: la luna cicla 15/30/60 min y apaga la radio al cumplirse.
  const sleepTimer = useRef(null);
  useEffect(() => {
    clearTimeout(sleepTimer.current);
    const mins = SLEEP_STEPS[sleepIdx];
    if (mins > 0) {
      sleepTimer.current = setTimeout(() => {
        stopStream();
        setSleepIdx(0);
      }, mins * 60 * 1000);
    }
    return () => clearTimeout(sleepTimer.current);
  }, [sleepIdx]);

  const loadProgram = useCallback(() => {
    setUpcoming(null);
    fetch(BASE + "/api/state", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setUpcoming(((d && d.upcoming) || []).slice(0, 6)))
      .catch(() => setUpcoming([]));
    fetch(BASE + "/api/programa", { cache: "no-store" })
      .then((r) => r.json())
      .then(setProg)
      .catch(() => {});
  }, []);

  const go = (name) => {
    setTab(name);
    if (name === "programa") loadProgram();
  };

  const chips = [];
  const time = ctx.time || {}, w = ctx.weather || {};
  if (time.period) chips.push({ txt: PERIODS[time.period] || time.period, hot: true });
  if (np.album) chips.push({ txt: np.album.replace("Kultura Radio - ", "") });
  if (w.temp != null) chips.push({ txt: w.temp + "°" + (w.tempUnit || "F") + " · Raleigh" });

  const sleepMins = SLEEP_STEPS[sleepIdx];

  return (
    <View style={[s.app, { paddingTop: insets.top }]}>
      <StatusBar barStyle="light-content" backgroundColor="transparent" translucent />
      {/* Fondo degradado: una SOLA capa de borde a borde, sin formas
          recortadas; en Radio el tope es mas calido. */}
      <LinearGradient
        colors={tab === "radio" ? T.gradRadio : T.grad}
        locations={[0, 0.42, 0.85]}
        style={StyleSheet.absoluteFill}
      />
      {/* Skins con paisaje (paises): la imagen va sobre el degradado (que
          cubre mientras carga) y un velo oscuro encima garantiza lectura:
          fuerte arriba (logo/chips), suave al centro (que luzca la bandera),
          fuerte abajo (pestañas). */}
      {!!T.fondo && (
        <>
          <Image source={{ uri: T.fondo }} resizeMode="cover" style={StyleSheet.absoluteFill} />
          <LinearGradient
            colors={["rgba(7,23,37,0.62)", "rgba(7,23,37,0.28)", "rgba(7,23,37,0.16)", "rgba(7,23,37,0.55)", "rgba(7,23,37,0.82)"]}
            locations={[0, 0.3, 0.55, 0.82, 1]}
            style={StyleSheet.absoluteFill}
          />
        </>
      )}
      {/* Atmosfera del tema: nieve+luces, estrellas, palmas o chispas */}
      <Ambient themeKey={themeKey} cielo={!!T.cielo} lightsTop={insets.top + 52} />

      {/* TOP BAR */}
      <View style={s.topbar}>
        {T.markGrad ? (
          <LinearGradient colors={T.markGrad} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.mark}>
            <Text style={[s.markK, { color: "#FFFFFF" }]}>K</Text>
          </LinearGradient>
        ) : (
          <View style={s.mark}><Text style={s.markK}>K</Text></View>
        )}
        <View>
          <Text style={s.brandH}>Kultura Radio</Text>
          <Text style={s.brandP}>LA QUE NOS UNE</Text>
        </View>
        <View style={s.topRight}>
          <Pressable onPress={() => setSleepIdx((sleepIdx + 1) % SLEEP_STEPS.length)} style={s.moonBtn}>
            <Ionicons name="moon-outline" size={17} color={sleepMins ? T.amber : T.muted} />
            {sleepMins > 0 && <Text style={s.moonTxt}>{sleepMins}</Text>}
          </Pressable>
          <View style={[s.livePill, online === false && s.livePillOff]}>
            <View style={[s.dot, online && s.dotOn]} />
            <Text style={s.livePillTxt}>
              {online == null ? "CONECTANDO" : online ? "EN VIVO" : "SIN SEÑAL"}
            </Text>
          </View>
          <Text style={s.ver}>{APP_VER}</Text>
        </View>
      </View>

      {/* CONTENIDO */}
      <ScrollView style={s.flex} contentContainerStyle={{ flexGrow: 1, paddingBottom: 108 + insets.bottom }}>
        {tab === "radio" && (
          <View style={s.hero}>
            <View style={s.halo}>
              <PulseRing size={236} color={T.amber + "55"} delay={0} />
              <PulseRing size={236} color={T.amber + "4D"} delay={1300} />
              <SpinningVinyl key={themeKey} playing={playing} art={np.art} />
              <ToneArm playing={playing} />
              <Pressable onPress={toggle} style={({ pressed }) => [s.play, pressed && { transform: [{ scale: 0.94 }] }]}>
                <LinearGradient colors={T.playGrad} style={s.playGrad}>
                  <Ionicons name={playing ? "pause" : "play"} size={34} color={T.dark} style={!playing && { marginLeft: 4 }} />
                </LinearGradient>
              </Pressable>
            </View>
            {np.live ? (
              <View style={s.onair}><View style={s.onairDot} /><Text style={s.onairTxt}>EN VIVO</Text></View>
            ) : (
              <Text style={s.label}>AHORA SUENA</Text>
            )}
            <Text style={s.npTitle}>{np.title}</Text>
            <Text style={s.npArtist}>{np.artist}</Text>
            <View style={s.chips}>
              {chips.map((ch, i) => (
                <View key={i} style={s.chip}>
                  <Text style={[s.chipTxt, ch.hot && { color: T.amber, fontFamily: "Outfit_600SemiBold" }]}>{ch.txt}</Text>
                </View>
              ))}
            </View>
            <View style={s.wave}>
              {Array.from({ length: 23 }, (_, i) => (
                <WaveBar
                  key={i}
                  seed={i + 3}
                  playing={playing}
                  color={T.barras ? T.barras[i % T.barras.length] : themeKey === "navidad" ? LIGHT_COLORS[i % 3] : null}
                />
              ))}
            </View>
          </View>
        )}

        {tab === "pedir" && <Pedir />}

        {tab === "programa" && (
          <View style={s.screen}>
            <Text style={s.kicker}>EN EL AIRE</Text>
            <View style={s.card}>
              <Text style={s.cardH}>{prog?.ahora?.nombre || "Programación continua"}</Text>
              <Text style={s.cardP}>{prog?.ahora?.desc || "El DJ Kultura elige la música según la hora y el ambiente."}</Text>
            </View>
            <Text style={s.kicker}>HOY EN KULTURA</Text>
            <View style={s.card}>
              {prog == null && <Text style={s.cardP}>Cargando…</Text>}
              {prog && (prog.hoy_lista || []).map((x, i, arr) => {
                const on = prog.ahora && x.id === prog.ahora.id;
                const fmtH = (h) => (h % 12 || 12) + (h < 12 ? ":00 am" : ":00 pm");
                return (
                  <View key={i} style={[s.row, i === arr.length - 1 && { borderBottomWidth: 0 }]}>
                    <View style={s.flex}>
                      <Text style={[s.rowT, on && { color: T.amber }]} numberOfLines={1}>
                        {x.nombre}{on ? " · en el aire" : ""}
                      </Text>
                      <Text style={s.rowA}>{fmtH(x.desde)} – {fmtH(x.hasta)}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
            <Text style={s.kicker}>LO QUE VIENE</Text>
            <View style={s.card}>
              {upcoming == null && <Text style={s.cardP}>Cargando…</Text>}
              {upcoming && upcoming.length === 0 && <Text style={s.cardP}>El DJ está eligiendo lo que viene…</Text>}
              {upcoming && upcoming.map((song, i) => (
                <View key={i} style={[s.row, i === upcoming.length - 1 && { borderBottomWidth: 0 }]}>
                  <Text style={s.rowN}>{i + 1}</Text>
                  <View style={s.flex}>
                    <Text style={s.rowT} numberOfLines={1}>{song.title || "—"}</Text>
                    <Text style={s.rowA} numberOfLines={1}>{song.artist || ""}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {tab === "mas" && <Mas themeKey={themeKey} setThemeKey={setThemeKey} />}
      </ScrollView>

      {/* MINI PLAYER */}
      {tab !== "radio" && (
        <View style={[s.mini, { bottom: 92 + insets.bottom }]}>
          {np.art ? (
            <Image source={{ uri: np.art }} style={s.miniArtImg} />
          ) : (
            <View style={s.miniArt}><Text style={s.miniK}>K</Text></View>
          )}
          <View style={s.flex}>
            <Text style={s.miniT} numberOfLines={1}>{np.title}</Text>
            <Text style={s.miniA} numberOfLines={1}>{np.artist}</Text>
          </View>
          <Pressable onPress={toggle} style={s.miniBtn}>
            <Ionicons name={playing ? "pause" : "play"} size={20} color={T.dark} style={!playing && { marginLeft: 2 }} />
          </Pressable>
        </View>
      )}

      {/* TAB BAR PILDORA */}
      <View style={[s.tabwrap, { paddingBottom: insets.bottom + 10 }]}>
        <View style={s.tabbar}>
          {[
            ["radio", "radio-outline", "Radio"],
            ["pedir", "musical-notes-outline", "Pedir"],
            ["programa", "time-outline", "Programa"],
            ["mas", "ellipsis-horizontal", "Más"],
          ].map(([key, icon, label]) => (
            <Pressable key={key} onPress={() => go(key)} style={s.tab}>
              <Ionicons name={icon} size={20} color={tab === key ? T.amber : T.muted} />
              <Text style={[s.tabTxt, tab === key && { color: T.amber }]}>{label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </View>
  );
}

// El interprete del sistema lee "repite X" como "repetir la actual" y bota el
// titulo. Normalizamos "repite/vuelve a poner/otra vez X" -> "pon X".
function normReq(t) {
  const m = t.match(/^\s*(rep[ií]te(?:me|la|lo)?|rep[eé]te(?:la|lo)?|vuelve a poner|ponme de nuevo|ponme otra vez|otra vez|de nuevo|dale otra vez)\s+(.+)$/i);
  return m && m[2] ? "pon " + m[2].trim() : t.trim();
}

function Pedir() {
  const { T, s } = useTheme();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [ack, setAck] = useState(null);
  const [left, setLeft] = useState(0);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [rec, setRec] = useState("idle"); // idle | rec | done | sending
  const [dediAck, setDediAck] = useState(null);
  const recTimer = useRef(null);
  const previewRef = useRef(null);

  // ---- Autocompletado del catalogo: mientras escribe, la app muestra lo que
  // SI existe en la biblioteca; al tocar una, el pedido va exacto y el DJ no
  // tiene que interpretar nada.
  const [sugs, setSugs] = useState([]);
  const sugTimer = useRef(null);

  function onSongText(t) {
    setText(t);
    clearTimeout(sugTimer.current);
    if (t.trim().length < 2) { setSugs([]); return; }
    sugTimer.current = setTimeout(() => {
      fetch(BASE + "/api/songs?q=" + encodeURIComponent(t.trim()))
        .then((r) => r.json())
        .then((d) => setSugs(((d && d.songs) || []).slice(0, 5)))
        .catch(() => setSugs([]));
    }, 350);
  }

  function pickSug(sg) {
    setText(sg.title + " de " + sg.artist);
    setSugs([]);
  }

  useEffect(() => {
    AsyncStorage.getItem("kr_name").then((v) => v && setName(v)).catch(() => {});
    refreshCooldown();
    const id = setInterval(refreshCooldown, 30000);
    return () => {
      clearInterval(id);
      clearTimeout(recTimer.current);
      clearTimeout(sugTimer.current);
      try { if (previewRef.current) previewRef.current.release(); } catch (e) {}
    };
  }, []);

  async function refreshCooldown() {
    try {
      const last = parseInt((await AsyncStorage.getItem("kr_last_req")) || "0", 10) || 0;
      setLeft(Math.max(0, REQ_COOLDOWN_MS - (Date.now() - last)));
    } catch (e) {}
  }

  function pollReq(id, n) {
    if (n > 12) { setAck({ msg: "¡Va para ti! Suena en un rato. 🎶", color: T.teal }); return; }
    fetch(BASE + "/api/request/" + id, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (d && d.ack) setAck({ msg: d.ack, color: T.teal });
        else if (d && d.status === "failed") setAck({ msg: d.message || "No la encontré, prueba con otra.", color: T.amber });
        else setTimeout(() => pollReq(id, n + 1), 2000);
      })
      .catch(() => setTimeout(() => pollReq(id, n + 1), 2000));
  }

  async function send() {
    if (left > 0) {
      const m = Math.ceil(left / 60000);
      setAck({ msg: "Ya pediste tu canción 🎶 Puedes pedir otra en " + m + (m === 1 ? " minuto." : " minutos."), color: T.muted });
      return;
    }
    const t = normReq(text.trim());
    if (!t) return;
    const who = name.trim() || "mi gente";
    try { await AsyncStorage.setItem("kr_name", name.trim()); } catch (e) {}
    setAck({ msg: "Enviando al DJ…", color: T.muted });
    fetch(BASE + "/api/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: t, name: who }),
    })
      .then((r) => r.json())
      .then(async (d) => {
        if (d && d.requestId) {
          setText("");
          try { await AsyncStorage.setItem("kr_last_req", String(Date.now())); } catch (e) {}
          refreshCooldown();
          pollReq(d.requestId, 0);
        } else setAck({ msg: (d && d.message) || "Dale play primero para pedir 🎧", color: T.amber });
      })
      .catch(() => setAck({ msg: "No se pudo enviar, intenta de nuevo.", color: T.amber }));
  }

  async function startRec() {
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setDediAck({ msg: "Sin permiso de micrófono no puedo grabar tu dedicatoria.", color: T.amber });
        return;
      }
      setDediAck(null);
      await enterRecordMode();
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRec("rec");
      recTimer.current = setTimeout(stopRec, 15000);
    } catch (e) {
      setDediAck({ msg: "No pude iniciar la grabación, intenta de nuevo.", color: T.amber });
      exitRecordMode().catch(() => {});
      setRec("idle");
    }
  }

  async function stopRec() {
    clearTimeout(recTimer.current);
    try { await recorder.stop(); } catch (e) {}
    await exitRecordMode().catch(() => {});
    setRec("done");
  }

  function playPreview() {
    try {
      // Pausa la radio mientras suena el preview y la reanuda al terminar.
      const radioSonaba = !!player.playing;
      stopStream();
      if (previewRef.current) previewRef.current.release();
      const p = createAudioPlayer(recorder.uri);
      previewRef.current = p;
      p.addListener("playbackStatusUpdate", (st) => {
        if (st && st.didJustFinish) {
          try { p.release(); } catch (e) {}
          if (previewRef.current === p) previewRef.current = null;
          if (radioSonaba) startStream().catch(() => {});
        }
      });
      p.play();
    } catch (e) {}
  }

  async function sendDedi() {
    if (!recorder.uri) return;
    setRec("sending");
    setDediAck({ msg: "Revisando tu dedicatoria…", color: T.muted });
    try {
      const b64 = await FileSystem.readAsStringAsync(recorder.uri, { encoding: FileSystem.EncodingType.Base64 });
      const ext = (recorder.uri.split(".").pop() || "m4a").toLowerCase();
      const who = name.trim() || "mi gente";
      try { await AsyncStorage.setItem("kr_name", name.trim()); } catch (e) {}
      const r = await fetch(BASE + "/api/dedi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: who, song: normReq(text.trim()), audio: b64, ext: ext }),
      });
      const d = await r.json();
      if (d && d.status === "ok") {
        setDediAck({ msg: d.message || "¡Tu dedicatoria va al aire! 🎙", color: T.teal });
        setRec("idle");
        setText("");
      } else {
        setDediAck({ msg: (d && d.message) || "No se pudo enviar, intenta de nuevo.", color: T.amber });
        setRec("done");
      }
    } catch (e) {
      setDediAck({ msg: "No se pudo enviar, revisa tu señal e intenta de nuevo.", color: T.amber });
      setRec("done");
    }
  }

  function discardRec() {
    try { if (previewRef.current) previewRef.current.release(); } catch (e) {}
    previewRef.current = null;
    setRec("idle");
    setDediAck(null);
  }

  // Un solo boton de envio: con voz grabada va todo junto por /api/dedi
  // (saludo + cancion); sin voz, es el pedido de texto de siempre.
  function sendAll() {
    setAck(null);
    setDediAck(null);
    if (rec === "done") sendDedi();
    else send();
  }

  const hasVoice = rec === "done" || rec === "sending";
  // Bloqueado mientras GRABA (rec) y mientras ENVIA (sending): solo se envia
  // en reposo o con la grabacion ya terminada.
  const canSend = (rec === "idle" || rec === "done") && (text.trim().length > 0 || hasVoice);

  return (
    <View style={s.screen}>
      <Text style={s.kickerBig}>
        DEDICA CON <Text style={{ color: T.amber }}>TU VOZ</Text>
      </Text>
      <Text style={s.dediIntro}>
        Graba un saludo de hasta 15 segundos: suena al aire justo cuando arranque
        tu canción. O pide tu canción sin voz, como siempre.
      </Text>

      {/* MIC GRANDE */}
      <View style={s.dediZone}>
        {rec === "idle" && (
          <Pressable onPress={startRec} style={s.bigMicWrap}>
            <PulseRing size={168} color={T.terra + "73"} delay={0} />
            <PulseRing size={168} color={T.terra + "66"} delay={1400} />
            <LinearGradient colors={T.micGrad} style={s.bigMic}>
              <Ionicons name="mic" size={40} color={T.cream} />
            </LinearGradient>
          </Pressable>
        )}
        {rec === "rec" && (
          <Pressable onPress={stopRec} style={s.bigMicWrap}>
            <PulseRing size={168} color="rgba(225,29,46,0.6)" delay={0} />
            <PulseRing size={168} color="rgba(225,29,46,0.5)" delay={900} />
            <View style={[s.bigMic, { backgroundColor: T.red }]}>
              <Ionicons name="stop" size={38} color="#fff" />
            </View>
          </Pressable>
        )}
        {hasVoice && (
          <View style={s.recRow}>
            <Pressable onPress={playPreview} style={s.recSmall}>
              <Ionicons name="play" size={18} color={T.cream} />
            </Pressable>
            <Pressable onPress={startRec} style={s.recSmall}>
              <Ionicons name="refresh" size={18} color={T.cream} />
            </Pressable>
            <Pressable onPress={discardRec} style={s.recSmall}>
              <Ionicons name="trash-outline" size={18} color={T.cream} />
            </Pressable>
            <View style={s.recChip}>
              <Text style={s.recChipTxt}>Tu dedicatoria está lista 🎙</Text>
            </View>
          </View>
        )}
        {rec === "idle" && <Text style={s.dediHint}>TOCA PARA GRABAR</Text>}
        {rec === "rec" && <Text style={[s.dediHint, { color: T.red }]}>GRABANDO… TOCA PARA PARAR</Text>}
      </View>

      {/* CANCION + NOMBRE */}
      <View style={s.card}>
        <Text style={s.cardQ}>¿Y qué canción va con tu saludo?</Text>
        <TextInput
          style={s.input}
          placeholder="Ej: una bachata de Romeo Santos"
          placeholderTextColor={T.muted}
          value={text}
          onChangeText={onSongText}
          maxLength={120}
        />
        {sugs.length > 0 && (
          <View style={s.sugBox}>
            {sugs.map((sg, i) => (
              <Pressable key={i} onPress={() => pickSug(sg)} style={[s.sugRow, i === sugs.length - 1 && { borderBottomWidth: 0 }]}>
                <Ionicons name="musical-note" size={13} color={T.amber} />
                <Text style={s.sugT} numberOfLines={1}>{sg.title}</Text>
                <Text style={s.sugA} numberOfLines={1}> · {sg.artist}</Text>
              </Pressable>
            ))}
            <Text style={s.sugHint}>En la biblioteca: toca una para pedirla exacta</Text>
          </View>
        )}
        <TextInput
          style={s.input}
          placeholder="Tu nombre (para que el DJ te salude)"
          placeholderTextColor={T.muted}
          value={name}
          onChangeText={setName}
          maxLength={24}
        />
      </View>

      <Pressable onPress={sendAll} disabled={!canSend} style={[s.sendWrap, !canSend && { opacity: 0.5 }]}>
        <LinearGradient colors={T.sendGrad} style={s.sendBtn}>
          <Ionicons name="send" size={18} color={T.dark} />
          <Text style={s.sendTxt}>
            {rec === "sending"
              ? "Enviando…"
              : hasVoice
                ? (text.trim() ? "Enviar dedicatoria y canción" : "Enviar mi dedicatoria")
                : "Enviar al DJ"}
          </Text>
        </LinearGradient>
      </Pressable>
      {ack && <Text style={[s.ack, { color: ack.color }]}>{ack.msg}</Text>}
      {dediAck && <Text style={[s.ack, { color: dediAck.color }]}>{dediAck.msg}</Text>}
      <Text style={s.dediFoot}>Moderado automáticamente · un saludo cada 10 min</Text>
    </View>
  );
}

function Mas({ themeKey, setThemeKey }) {
  const { T, s } = useTheme();
  const [contact, setContact] = useState("");
  const [ack, setAck] = useState("");
  // Redes sociales desde el servidor (redes.json): agregar o cambiar una red
  // no requiere actualizar la app.
  const [redes, setRedes] = useState([]);
  // "Tu voz en Kultura" (WhatsApp) y "Apoya a Kultura" (donaciones): se
  // encienden desde participa.json y apoya.json; sin esos archivos activos
  // las tarjetas no aparecen. Cero rebuilds para prenderlas o cambiarlas.
  const [voz, setVoz] = useState(null);
  const [apoya, setApoya] = useState(null);
  useEffect(() => {
    const t = Date.now();
    fetch(BASE + "/redes.json?t=" + t)
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d && d.redes)) setRedes(d.redes); })
      .catch(() => {});
    fetch(BASE + "/participa.json?t=" + t)
      .then((r) => r.json())
      .then((d) => { if (d && d.activo && d.numero) setVoz(d); })
      .catch(() => {});
    fetch(BASE + "/apoya.json?t=" + t)
      .then((r) => r.json())
      .then((d) => { if (d && d.activo && d.url) setApoya(d); })
      .catch(() => {});
  }, []);
  function abrirVoz() {
    Linking.openURL(
      "https://wa.me/" + String(voz.numero).replace(/\D/g, "") +
      "?text=" + encodeURIComponent(voz.mensaje || "Hola Kultura")
    ).catch(() => {});
  }
  function compartir() {
    Share.share({
      message:
        "🎶 ¡Te recomiendo Kultura Radio!\n" +
        "La música latina que nos conecta con nuestras raíces.\n" +
        "🎧 Salsa, bachata, merengue y mucho más.\n" +
        "KULTURA RADIO. La que nos une. ❤️\n" +
        "📲 Escúchala gratis: https://kulturaradio.com/app",
    }).catch(() => {});
  }
  function sendAd() {
    const v = contact.trim();
    if (!v) return;
    Linking.openURL(
      "mailto:hola@kulturaradio.com?subject=" + encodeURIComponent("Anunciante - Kultura Radio") +
      "&body=" + encodeURIComponent("Quiero anunciarme en Kultura Radio.\n\nContacto: " + v)
    ).catch(() => {});
    setAck("¡Gracias! Se abre tu correo para enviarnos los datos.");
  }
  return (
    <View style={s.screen}>
      <Text style={s.kicker}>TEMA DE LA APP</Text>
      <View style={[s.card, { paddingVertical: 14 }]}>
        <View style={s.themeRow}>
          {Object.entries(THEMES).map(([k, t]) => (
            <Pressable key={k} onPress={() => setThemeKey(k)} style={s.themeItem}>
              <View style={[s.themeSwatch, themeKey === k && { borderColor: T.amber }]}>
                <LinearGradient colors={[t.amber, t.terra]} style={s.flex} />
              </View>
              <Text style={[s.themeName, themeKey === k && { color: T.amber }]}>{t.name}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <Text style={s.kicker}>ANÚNCIATE CON NOSOTROS</Text>
      <View style={s.card}>
        <Text style={s.cardH}>Tu negocio en la radio que nos une</Text>
        <Text style={s.cardP}>Llega a toda la comunidad latina del Triangle.</Text>
        <TextInput
          style={s.input}
          placeholder="Nombre y teléfono / negocio"
          placeholderTextColor={T.muted}
          value={contact}
          onChangeText={setContact}
          maxLength={120}
        />
        <Pressable onPress={sendAd} style={s.sendWrap}>
          <LinearGradient colors={T.sendGrad} style={s.sendBtn}>
            <Text style={s.sendTxt}>Pedir info</Text>
          </LinearGradient>
        </Pressable>
        {!!ack && <Text style={[s.ack, { color: T.teal }]}>{ack}</Text>}
      </View>

      {voz && (
        <>
          <Text style={s.kicker}>TU VOZ EN KULTURA</Text>
          <View style={s.card}>
            <Text style={s.cardH}>Tu voz también es parte de Kultura</Text>
            <Text style={s.cardP}>{voz.sub || "Comparte tus historias, tradiciones y experiencias con nuestra comunidad"}</Text>
            <Pressable onPress={abrirVoz} style={s.sendWrap}>
              <LinearGradient colors={T.sendGrad} style={[s.sendBtn, { flexDirection: "row", gap: 8 }]}>
                <Ionicons name="logo-whatsapp" size={18} color={T.dark} />
                <Text style={s.sendTxt}>{voz.boton || "Tu voz en Kultura"}</Text>
              </LinearGradient>
            </Pressable>
          </View>
        </>
      )}

      {redes.length > 0 && (
        <>
          <Text style={s.kicker}>SÍGUENOS</Text>
          <View style={s.card}>
          <View style={{ flexDirection: "row", justifyContent: "space-around" }}>
            {redes.map((r) => (
              <Pressable key={r.id} onPress={() => Linking.openURL(r.url).catch(() => {})} style={{ alignItems: "center", gap: 5 }}>
                <View style={{ width: 46, height: 46, borderRadius: 23, backgroundColor: T.surface2, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: T.faint }}>
                  <Ionicons name={"logo-" + r.id} size={22} color={T.amber} />
                </View>
                <Text style={{ fontFamily: "Outfit_400Regular", fontSize: 10.5, color: T.muted }}>{r.nombre}</Text>
              </Pressable>
            ))}
          </View>
          </View>
        </>
      )}

      <Text style={s.kicker}>COMPARTE</Text>
      <View style={s.card}>
        <Pressable onPress={compartir} style={s.sendWrap}>
          <LinearGradient colors={T.sendGrad} style={s.sendBtn}>
            <Text style={s.sendTxt}>Comparte Kultura</Text>
          </LinearGradient>
        </Pressable>
      </View>

      {apoya && (
        <>
          <Text style={s.kicker}>APOYA A KULTURA</Text>
          <View style={s.card}>
            <Text style={s.cardH}>{apoya.titulo || "Mantén viva la radio que nos une"}</Text>
            <Text style={s.cardP}>{apoya.sub || "Tu aporte, del tamaño que quieras, ayuda a que Kultura siga sonando."}</Text>
            <Pressable onPress={() => Linking.openURL(apoya.url).catch(() => {})} style={s.sendWrap}>
              <LinearGradient colors={T.playGrad} style={[s.sendBtn, { flexDirection: "row", gap: 8 }]}>
                <Ionicons name="heart" size={18} color={T.dark} />
                <Text style={s.sendTxt}>{apoya.boton || "Apoya a Kultura"}</Text>
              </LinearGradient>
            </Pressable>
          </View>
        </>
      )}

      <View style={s.mission}>
        <Text style={s.missionP}>"Música, cultura y comunidad: la voz de todos los latinos del Triangle."</Text>
        <Text style={s.missionS}>KULTURA RADIO · RALEIGH, NC · APP {APP_VER}</Text>
        <Pressable onPress={() => Linking.openURL(BASE + "/privacidad").catch(() => {})} hitSlop={10}>
          <Text style={[s.missionS, { marginTop: 10, textDecorationLine: "underline" }]}>Política de privacidad</Text>
        </Pressable>
      </View>
    </View>
  );
}

const makeStyles = (T) => StyleSheet.create({
  flex: { flex: 1 },
  app: { flex: 1, backgroundColor: T.bg },

  topbar: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 18, paddingVertical: 10,
  },
  mark: {
    width: 34, height: 34, borderRadius: 10, backgroundColor: T.terra,
    alignItems: "center", justifyContent: "center",
    shadowColor: T.terra, shadowOpacity: 0.45, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6,
  },
  markK: { fontFamily: "Fraunces_700Bold", fontSize: 21, color: T.cream, marginTop: -2 },
  brandH: { fontFamily: "Fraunces_600SemiBold", fontSize: 16, color: T.cream },
  brandP: { fontFamily: "Outfit_400Regular", fontSize: 8.5, color: T.amber, letterSpacing: 2.4, marginTop: 3 },
  topRight: { marginLeft: "auto", flexDirection: "row", alignItems: "center", gap: 9 },
  moonBtn: { flexDirection: "row", alignItems: "center", gap: 3, padding: 4 },
  moonTxt: { fontFamily: "Outfit_600SemiBold", fontSize: 11, color: T.amber },
  livePill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: T.teal + "29", borderWidth: 1, borderColor: T.teal + "59",
    borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5,
  },
  livePillOff: { backgroundColor: "rgba(140,140,150,0.14)", borderColor: "rgba(160,160,170,0.35)" },
  livePillTxt: { fontFamily: "Outfit_400Regular", fontSize: 8.5, letterSpacing: 1.6, color: T.cream },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#6b6258" },
  dotOn: { backgroundColor: T.teal },
  ver: { fontFamily: "Outfit_400Regular", fontSize: 9, color: T.muted, opacity: 0.6 },

  hero: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 22, paddingTop: 14 },
  halo: { width: 236, height: 236, alignItems: "center", justifyContent: "center", marginBottom: 24 },
  play: {
    position: "absolute", bottom: -4, right: 2, width: 76, height: 76, borderRadius: 38,
    shadowColor: T.amber, shadowOpacity: 0.55, shadowRadius: 16, shadowOffset: { width: 0, height: 10 }, elevation: 12,
  },
  playGrad: { flex: 1, borderRadius: 38, alignItems: "center", justifyContent: "center" },
  label: { fontFamily: "BebasNeue_400Regular", fontSize: 15, letterSpacing: 5, color: T.muted, marginBottom: 7 },
  onair: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: T.red,
    paddingHorizontal: 11, paddingVertical: 4, borderRadius: 999, marginBottom: 8,
  },
  onairDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#fff" },
  onairTxt: { fontFamily: "Outfit_600SemiBold", fontSize: 11, color: "#fff", letterSpacing: 1.5 },
  npTitle: { fontFamily: "Fraunces_600SemiBold", fontSize: 27, color: T.cream, textAlign: "center", lineHeight: 32 },
  npArtist: { fontFamily: "Outfit_400Regular", fontSize: 15, color: T.amber, textAlign: "center", marginTop: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 8, marginTop: 15 },
  chip: {
    backgroundColor: T.surface + "DD", borderWidth: 1, borderColor: T.faint,
    borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6,
  },
  chipTxt: { fontFamily: "Outfit_400Regular", fontSize: 10.5, color: T.cream, letterSpacing: 0.4 },
  wave: { flexDirection: "row", alignItems: "flex-end", gap: 3, height: 46, marginTop: 22 },
  waveBar: { width: 3.5, height: 46, borderRadius: 2, backgroundColor: T.amber, opacity: 0.9 },

  screen: { padding: 18 },
  kicker: { fontFamily: "BebasNeue_400Regular", fontSize: 16, letterSpacing: 3, color: T.muted, marginTop: 6, marginBottom: 10 },
  kickerBig: { fontFamily: "BebasNeue_400Regular", fontSize: 30, letterSpacing: 2.5, color: T.cream, marginTop: 4 },
  dediIntro: { fontFamily: "Outfit_400Regular", fontSize: 12.5, color: T.muted, lineHeight: 19, marginTop: 7 },
  dediZone: { alignItems: "center", paddingVertical: 22 },
  bigMicWrap: { width: 168, height: 168, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  bigMic: {
    width: 116, height: 116, borderRadius: 58, alignItems: "center", justifyContent: "center",
    shadowColor: T.terra, shadowOpacity: 0.55, shadowRadius: 20, shadowOffset: { width: 0, height: 12 }, elevation: 12,
  },
  dediHint: { fontFamily: "BebasNeue_400Regular", fontSize: 14, letterSpacing: 3, color: T.cream },
  recRow: { flexDirection: "row", alignItems: "stretch", gap: 8, marginBottom: 10 },
  recSmall: {
    width: 46, height: 46, borderRadius: 12, backgroundColor: T.surface2, borderWidth: 1,
    borderColor: T.faint, alignItems: "center", justifyContent: "center",
  },
  recChip: {
    flex: 1, borderRadius: 12, backgroundColor: T.surface2, borderWidth: 1,
    borderColor: T.faint, alignItems: "center", justifyContent: "center", paddingHorizontal: 10,
  },
  recChipTxt: { fontFamily: "Outfit_400Regular", fontSize: 12, color: T.cream },

  card: { backgroundColor: T.surface + "E6", borderWidth: 1, borderColor: T.faint, borderRadius: 18, padding: 16, marginBottom: 13 },
  cardH: { fontFamily: "Fraunces_600SemiBold", fontSize: 16, color: T.cream, marginBottom: 6 },
  cardP: { fontFamily: "Outfit_400Regular", fontSize: 13, color: T.muted, lineHeight: 21 },
  cardQ: { fontFamily: "Outfit_400Regular", fontSize: 11.5, color: T.muted, letterSpacing: 0.4, marginBottom: 2 },
  sugBox: {
    backgroundColor: T.bg, borderWidth: 1, borderColor: T.amber + "4D",
    borderRadius: 12, marginTop: 6, paddingHorizontal: 12, paddingTop: 2,
  },
  sugRow: {
    flexDirection: "row", alignItems: "center", gap: 7, paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: T.faint,
  },
  sugT: { fontFamily: "Outfit_500Medium", fontSize: 13, color: T.cream, flexShrink: 1 },
  sugA: { fontFamily: "Outfit_400Regular", fontSize: 12, color: T.amber, flexShrink: 1 },
  sugHint: { fontFamily: "Outfit_400Regular", fontSize: 9.5, color: T.muted, paddingVertical: 7, textAlign: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: T.faint },
  rowN: { width: 22, fontFamily: "Outfit_400Regular", fontSize: 13, color: T.muted, textAlign: "center" },
  rowT: { fontFamily: "Outfit_500Medium", fontSize: 14, color: T.cream },
  rowA: { fontFamily: "Outfit_400Regular", fontSize: 12, color: T.amber },

  input: {
    backgroundColor: T.bg, borderWidth: 1, borderColor: T.faint, borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 12, color: T.cream,
    fontFamily: "Outfit_400Regular", fontSize: 14, marginTop: 10,
  },
  sendWrap: {
    marginTop: 4, borderRadius: 14,
    shadowColor: T.amber, shadowOpacity: 0.4, shadowRadius: 13, shadowOffset: { width: 0, height: 8 }, elevation: 8,
  },
  sendBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    borderRadius: 14, paddingVertical: 15,
  },
  sendTxt: { fontFamily: "Outfit_600SemiBold", fontSize: 14.5, color: T.dark },
  ack: { fontFamily: "Outfit_400Regular", fontSize: 14, marginTop: 12, lineHeight: 21 },
  dediFoot: { fontFamily: "Outfit_400Regular", fontSize: 10.5, color: T.muted, textAlign: "center", marginTop: 12 },

  themeRow: { flexDirection: "row", flexWrap: "wrap", justifyContent: "flex-start", rowGap: 16 },
  themeItem: { alignItems: "center", gap: 6, width: "25%" },
  themeSwatch: {
    width: 40, height: 40, borderRadius: 20, overflow: "hidden",
    borderWidth: 2.5, borderColor: "transparent",
  },
  themeName: { fontFamily: "Outfit_400Regular", fontSize: 10.5, color: T.muted },

  mission: { alignItems: "center", paddingVertical: 16, paddingHorizontal: 4 },
  missionP: { fontFamily: "Fraunces_600SemiBold", fontStyle: "italic", fontSize: 16, color: T.cream, textAlign: "center", lineHeight: 24, marginBottom: 8 },
  missionS: { fontFamily: "Outfit_400Regular", fontSize: 10, color: T.muted, letterSpacing: 1 },

  mini: {
    position: "absolute", left: 10, right: 10, flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 16,
    backgroundColor: T.surface2 + "FA", borderWidth: 1, borderColor: T.faint,
  },
  miniArt: { width: 38, height: 38, borderRadius: 9, backgroundColor: T.terra, alignItems: "center", justifyContent: "center" },
  miniArtImg: { width: 38, height: 38, borderRadius: 9 },
  miniK: { fontFamily: "Fraunces_700Bold", fontSize: 18, color: T.cream, marginTop: -2 },
  miniT: { fontFamily: "Outfit_500Medium", fontSize: 13, color: T.cream },
  miniA: { fontFamily: "Outfit_400Regular", fontSize: 11, color: T.amber },
  miniBtn: { width: 42, height: 42, borderRadius: 21, backgroundColor: T.amber, alignItems: "center", justifyContent: "center" },

  tabwrap: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 14 },
  tabbar: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: T.surface + "F2", borderWidth: 1, borderColor: T.faint,
    borderRadius: 999, paddingVertical: 8, paddingHorizontal: 10,
  },
  tab: { flex: 1, alignItems: "center", gap: 3, paddingVertical: 3 },
  tabTxt: { fontFamily: "Outfit_400Regular", fontSize: 9, color: T.muted, letterSpacing: 0.6 },
});

export default function App() {
  const [fontsLoaded] = useFonts({
    Fraunces_600SemiBold,
    Fraunces_700Bold,
    Outfit_400Regular,
    Outfit_500Medium,
    Outfit_600SemiBold,
    BebasNeue_400Regular,
  });
  const [themeKey, setThemeKeyRaw] = useState("oficial");
  // Skins remotos: primero el cache local (offline) y luego el servidor; si
  // el tema guardado del usuario es remoto, se re-aplica al llegar.
  const [temasV, setTemasV] = useState(0);
  const reaplicar = useCallback(() => {
    AsyncStorage.getItem("kr_theme")
      .then((v) => {
        if (v === "clasico" || v === "legado") v = "oficial"; // migracion: el terracota se retiro
        if (v && THEMES[v]) setThemeKeyRaw(v);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    reaplicar(); // tema guardado de la casa, sin esperar al servidor
    AsyncStorage.getItem("kr_themes_cache")
      .then((v) => {
        if (v && registrarTemas(JSON.parse(v)) > 0) {
          setTemasV((n) => n + 1);
          reaplicar();
        }
      })
      .catch(() => {})
      .finally(() => {
        fetch(BASE + "/themes.json?t=" + Date.now())
          .then((r) => r.json())
          .then((d) => {
            if (registrarTemas(d) > 0) {
              AsyncStorage.setItem("kr_themes_cache", JSON.stringify(d)).catch(() => {});
              setTemasV((n) => n + 1);
            }
            reaplicar();
          })
          .catch(() => reaplicar());
      });
  }, [reaplicar]);
  const setThemeKey = useCallback((k) => {
    if (!THEMES[k]) return;
    setThemeKeyRaw(k);
    AsyncStorage.setItem("kr_theme", k).catch(() => {});
  }, []);
  const themeValue = useMemo(() => {
    const T = THEMES[themeKey];
    return { T, s: makeStyles(T), themeKey, setThemeKey };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeKey, setThemeKey, temasV]);

  if (!fontsLoaded) return <View style={{ flex: 1, backgroundColor: THEMES[themeKey].bg }} />;
  return (
    <SafeAreaProvider>
      <ThemeCtx.Provider value={themeValue}>
        <Root />
      </ThemeCtx.Provider>
    </SafeAreaProvider>
  );
}
