(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var audio = $("audio");
  var STREAM = "/stream.mp3";
  var ICON = location.origin + "/icons/icon-512.png";
  var PLAY = '<path d="M8 5v14l11-7z"/>';
  var PAUSE = '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>';
  var playing = false, current = "", curTab = "radio";

  var disc = $("disc"), play = $("play"), playIcon = $("playIcon");
  var miBtn = $("miBtn"), miIcon = $("miIcon"), mini = $("mini");

  var starting = false, wantPlay = false;
  function renderPlay() {
    playIcon.innerHTML = playing ? PAUSE : PLAY;
    miIcon.innerHTML = playing ? PAUSE : PLAY;
    play.classList.toggle("playing", playing);
    disc.classList.toggle("spin", playing);
  }
  function start() {
    // Conexión fresca cada vez para enganchar el borde EN VIVO del stream.
    wantPlay = true;
    starting = true;
    try { audio.pause(); } catch (e) {}
    audio.src = STREAM + "?t=" + Date.now();
    try { audio.load(); } catch (e) {}
    var p = audio.play();
    if (p && p.then) {
      p.then(function () { starting = false; playing = true; renderPlay(); })
       .catch(function () { starting = false; playing = false; renderPlay(); });
    } else { starting = false; }
  }
  function stop() {
    wantPlay = false;
    starting = false;
    audio.pause();
    audio.removeAttribute("src");
    try { audio.load(); } catch (e) {}
    playing = false; renderPlay();
  }
  function toggle() { if (playing || starting) stop(); else start(); }
  play.addEventListener("click", toggle);
  miBtn.addEventListener("click", toggle);
  audio.addEventListener("playing", function () { starting = false; playing = true; renderPlay(); });
  // Solo refleja pausa real (cuando aún hay src); stop() ya limpia el estado.
  audio.addEventListener("pause", function () { if (audio.currentSrc) { playing = false; renderPlay(); } });
  audio.addEventListener("ended", function () { playing = false; renderPlay(); });
  audio.addEventListener("error", function () { starting = false; playing = false; renderPlay(); });

  // Resiliencia: si el oyente QUERÍA escuchar (wantPlay) y el audio se cortó
  // (carro apagado, Bluetooth, túnel, señal), reintenta reconectar solo cuando
  // la app vuelve al frente, regresa el internet, o cada pocos segundos.
  function resumeIfWanted() {
    if (wantPlay && !starting && audio.paused && navigator.onLine) start();
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) resumeIfWanted(); });
  window.addEventListener("online", resumeIfWanted);
  window.addEventListener("focus", resumeIfWanted);
  setInterval(resumeIfWanted, 8000);

  function setMedia(t, a) {
    if (!("mediaSession" in navigator)) return;
    var ms = navigator.mediaSession;
    var art = [{ src: ICON, sizes: "512x512", type: "image/png" }];
    // iOS a veces IGNORA el reemplazo del objeto metadata cuando la página está
    // en segundo plano / pantalla bloqueada, pero honra la MUTACIÓN del objeto
    // vivo — y en modo app instalada puede ser al revés. Hacemos AMBOS: mutar
    // el existente y luego reemplazarlo; entre las dos señales iOS repinta.
    var md = ms.metadata;
    if (md) {
      try { md.title = t; md.artist = a; md.album = "Kultura Radio"; md.artwork = art; } catch (e) {}
    }
    try {
      ms.metadata = new MediaMetadata({ title: t, artist: a, album: "Kultura Radio", artwork: art });
    } catch (e) {}
    try {
      ms.setActionHandler("play", start);
      ms.setActionHandler("pause", stop);
    } catch (e) {}
    // NOTA (jul 2026): en Safari esto actualiza la lock screen EN VIVO. En modo
    // app instalada (standalone) iOS NO repinta el Now Playing desde segundo
    // plano aunque la metadata se aplique (verificado con telemetría) — límite
    // de iOS para PWAs; la solución real es el wrap nativo (Capacitor) o HLS
    // con metadata incrustada.
  }

  var PERIODS = { morning: "Mañana", afternoon: "Tarde", evening: "Noche", night: "Noche", late: "Madrugada" };
  function chip(icon, txt) { return '<span class="chip"><i class="ti ' + icon + '"></i>' + txt + "</span>"; }

  var lastPoll = 0;
  function poll() {
    lastPoll = Date.now();
    fetch("/api/now-playing", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var np = (d && d.nowPlaying) || {}, ctx = (d && d.context) || {};
        var t = np.title || "Kultura Radio", a = np.artist || "la que nos une";
        if (t !== current) {
          current = t;
          $("npTitle").textContent = t; $("npArtist").textContent = a;
          $("miTitle").textContent = t; $("miArtist").textContent = a;
        }
        // Re-afirmar la metadata en CADA poll (no solo al cambiar): con la
        // pantalla bloqueada iOS puede ignorar una escritura puntual; la
        // repetición (~15s, montada sobre el heartbeat de timeupdate) le da
        // oportunidades continuas de repintar la lock screen.
        setMedia(t, a);
        var time = ctx.time || {}, w = ctx.weather || {}, chips = "";
        if (time.period) chips += chip("ti-clock-hour-4", PERIODS[time.period] || time.period);
        if (np.album) chips += chip("ti-disc", np.album.replace("Kultura Radio - ", ""));
        if (w.temp != null) chips += chip("ti-temperature", w.temp + "°" + (w.tempUnit || "F"));
        $("chips").innerHTML = chips;
        $("dot").classList.add("on"); $("liveTxt").textContent = "en vivo";
      })
      .catch(function () { $("dot").classList.remove("on"); $("liveTxt").textContent = "sin señal"; });
  }
  poll(); setInterval(poll, 15000);
  // iOS congela los timers con la pantalla bloqueada, pero 'timeupdate' del audio
  // sigue disparando mientras suena en segundo plano → lo usamos para refrescar
  // la canción en la lock screen (Media Session) aunque el setInterval esté dormido.
  audio.addEventListener("timeupdate", function () {
    if (Date.now() - lastPoll > 12000) poll();
  });
  // Al arrancar, refresca de una para que la lock screen muestre lo correcto.
  audio.addEventListener("playing", poll);

  function loadProgram() {
    fetch("/api/state", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var up = (d && d.upcoming) || [], html = "";
        if (!up.length) html = '<p style="color:var(--muted);font-size:13px">El DJ está eligiendo lo que viene…</p>';
        for (var i = 0; i < Math.min(up.length, 6); i++) {
          var s = up[i];
          html += '<div class="row"><div class="n">' + (i + 1) + '</div><div class="info"><div class="t">' +
            (s.title || "—") + '</div><div class="a">' + (s.artist || "") + "</div></div></div>";
        }
        $("upcoming").innerHTML = html;
      })
      .catch(function () { $("upcoming").innerHTML = '<p style="color:var(--muted);font-size:13px">No se pudo cargar.</p>'; });
  }

  // Tab navigation
  var tabs = document.querySelectorAll(".tab");
  function go(name) {
    curTab = name;
    document.querySelectorAll(".screen").forEach(function (s) { s.classList.toggle("active", s.getAttribute("data-tab") === name); });
    tabs.forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-go") === name); });
    mini.classList.toggle("show", name !== "radio");
    window.scrollTo(0, 0);
    if (name === "programa") loadProgram();
    if (name === "pedir") refreshReqState(true);
  }
  tabs.forEach(function (b) { b.addEventListener("click", function () { go(b.getAttribute("data-go")); }); });

  // Request — espera por dispositivo para no saturar la programacion (1 cada 15 min).
  var reqText = $("reqText"), reqAck = $("reqAck"), reqName = $("reqName"), reqSend = $("reqSend");
  var REQ_COOLDOWN_MS = 15 * 60 * 1000;
  try { reqName.value = localStorage.getItem("kr_name") || ""; } catch (e) {}
  function reqCooldownLeft() {
    var last = 0;
    try { last = parseInt(localStorage.getItem("kr_last_req") || "0", 10) || 0; } catch (e) {}
    return Math.max(0, REQ_COOLDOWN_MS - (Date.now() - last));
  }
  function refreshReqState(showMsg) {
    var left = reqCooldownLeft();
    reqSend.disabled = left > 0;
    reqSend.style.opacity = left > 0 ? "0.5" : "";
    if (left > 0 && showMsg) {
      var m = Math.ceil(left / 60000);
      reqAck.style.display = "block"; reqAck.style.color = "var(--muted)";
      reqAck.textContent = "Ya pediste tu canción 🎶 Puedes pedir otra en " + m + (m === 1 ? " minuto." : " minutos.");
    }
  }
  // El intérprete del sistema lee "repite X" como "repetir la canción actual" y
  // bota el título. Normalizamos "repite/vuelve a poner/otra vez X" → "pon X".
  function normReq(t) {
    var m = t.match(/^\s*(rep[ií]te(?:me|la|lo)?|rep[eé]te(?:la|lo)?|vuelve a poner|ponme de nuevo|ponme otra vez|otra vez|de nuevo|dale otra vez)\s+(.+)$/i);
    return (m && m[2]) ? "pon " + m[2].trim() : t.trim();
  }
  reqSend.addEventListener("click", function () {
    if (reqCooldownLeft() > 0) { refreshReqState(true); return; }
    var text = normReq(reqText.value.trim()); if (!text) return;
    var name = reqName.value.trim();
    try { localStorage.setItem("kr_name", name); } catch (e) {}
    if (!name) name = "mi gente";
    reqAck.style.display = "block"; reqAck.style.color = "var(--muted)"; reqAck.textContent = "Enviando al DJ…";
    fetch("/api/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text, name: name }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.requestId) {
          reqText.value = "";
          try { localStorage.setItem("kr_last_req", String(Date.now())); } catch (e) {}
          refreshReqState(false);
          pollReq(d.requestId, 0);
        } else { reqAck.style.color = "var(--amber)"; reqAck.textContent = (d && d.message) || "Dale play primero para pedir 🎧"; }
      })
      .catch(function () { reqAck.style.color = "var(--amber)"; reqAck.textContent = "No se pudo enviar, intenta de nuevo."; });
  });
  // Cuenta regresiva viva mientras estas en la pestana Pedir.
  setInterval(function () {
    if (curTab !== "pedir") return;
    var inCd = reqCooldownLeft() > 0;
    var showing = reqAck.textContent.indexOf("Ya pediste") === 0;
    if (inCd) refreshReqState(showing);
    else if (showing) { reqAck.textContent = ""; reqAck.style.display = "none"; reqSend.disabled = false; reqSend.style.opacity = ""; }
  }, 30000);
  function pollReq(id, n) {
    if (n > 12) { reqAck.style.color = "var(--teal)"; reqAck.textContent = "¡Va para ti! Suena en un rato. 🎶"; return; }
    fetch("/api/request/" + id, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.ack) { reqAck.style.color = "var(--teal)"; reqAck.textContent = d.ack; }
      else if (d && d.status === "failed") { reqAck.style.color = "var(--amber)"; reqAck.textContent = d.message || "No la encontré, prueba con otra."; }
      else setTimeout(function () { pollReq(id, n + 1); }, 2000);
    }).catch(function () { setTimeout(function () { pollReq(id, n + 1); }, 2000); });
  }

  // Advertise
  var adContact = $("adContact"), adAck = $("adAck");
  $("adSend").addEventListener("click", function () {
    var v = adContact.value.trim(); if (!v) return;
    location.href = "mailto:frpenalo@gmail.com?subject=" + encodeURIComponent("Anunciante - Kultura Radio") +
      "&body=" + encodeURIComponent("Quiero anunciarme en Kultura Radio.\n\nContacto: " + v);
    adAck.style.display = "block"; adAck.style.color = "var(--teal)"; adAck.textContent = "¡Gracias! Se abre tu correo para enviarnos los datos.";
  });

  // Install
  var deferred = null, installBtn = $("installBtn"), installTip = $("installTip");
  var standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (standalone) installBtn.style.display = "none";
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); deferred = e; });
  window.addEventListener("appinstalled", function () { installBtn.style.display = "none"; });
  installBtn.addEventListener("click", function () {
    if (deferred) { deferred.prompt(); if (deferred.userChoice) deferred.userChoice.then(function () { deferred = null; }); return; }
    installTip.classList.add("show");
    if (isIOS) installTip.innerHTML = "En <b>Safari</b>: toca el botón <b>Compartir</b> (cuadro con flecha ↑, abajo) y elige <b>Add to Home Screen</b>.";
    else installTip.innerHTML = "En <b>Chrome</b>: toca el menú <b>⋮</b> (arriba a la derecha) y elige <b>Instalar app</b> / <b>Agregar a pantalla de inicio</b>.";
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); });
  }
})();
