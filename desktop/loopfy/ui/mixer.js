/*
 * Loopfy mixer — roda dentro da página da LIVE (injetado pelo Loopfy no navegador controlado).
 *
 * Cria duas fontes virtuais, "Loopfy Câmera" e "Loopfy Microfone", que aparecem na lista de fontes da LIVE.
 *  - A BASE é sempre uma câmera e um microfone REAIS (apresentador ao vivo). Sem câmera real a fonte não abre.
 *  - Vídeos da marca entram SÓ quando o operador manda tocar (window.__loopfy.play). Não há loop,
 *    não há sequência automática e o microfone ao vivo continua misturado durante o vídeo.
 */
(() => {
  if (window.__loopfy || !navigator.mediaDevices) return;
  const CFG = Object.assign(
    { width: 1280, height: 720, fps: 30, camera: "", mic: "", duck: 0.25, clipVol: 1, clipHost: "https://loopfy.clips" },
    window.__LOOPFY_CFG || {}
  );
  const md = navigator.mediaDevices;
  const orig = { gum: md.getUserMedia.bind(md), enumerate: md.enumerateDevices.bind(md) };
  const VCAM = "loopfy-camera", VMIC = "loopfy-microfone";
  const NAME_CAM = "Loopfy Câmera", NAME_MIC = "Loopfy Microfone";

  const S = { built: null, building: null, clip: null, clipEl: null, status: "idle", lastError: "", mute: false, prev: null, queue: [], seqTotal: 0, seqIndex: 0 };
  const micLevel = () => (S.mute ? 0 : S.clipEl ? CFG.duck : 1);
  const applyMic = () => { if (S.built) S.built.micGain.gain.setTargetAtTime(micLevel(), S.built.ac.currentTime, 0.05); };

  const fakeInfo = (id, kind, label) => ({ deviceId: id, kind, label, groupId: "loopfy", toJSON() { return { deviceId: id, kind, label, groupId: "loopfy" }; } });

  async function pickReal(kind) {
    const all = await orig.enumerate();
    const want = (kind === "videoinput" ? CFG.camera : CFG.mic || "").toLowerCase();
    const list = all.filter((d) => d.kind === kind && !d.deviceId.startsWith("loopfy") && !/^loopfy/i.test(d.label || ""));
    if (!list.length) return null;
    if (want) { const m = list.find((d) => (d.label || "").toLowerCase().includes(want)); if (m) return m; }
    return list.find((d) => d.deviceId !== "default") || list[0];
  }

  async function build() {
    const cam = await pickReal("videoinput");
    if (!cam) throw new DOMException("Loopfy: nenhuma câmera real encontrada. A base da live precisa ser uma câmera ao vivo.", "NotFoundError");
    const mic = await pickReal("audioinput");
    let camStream;
    try {
      camStream = await orig.gum({ video: { deviceId: { exact: cam.deviceId }, width: { ideal: CFG.width }, height: { ideal: CFG.height } } });
    } catch (e) {
      S.lastError = `Não consegui abrir a câmera "${cam.label}" (${e.name}). ` + (/obs/i.test(cam.label) ? "Ela é a câmera virtual do OBS: abra o OBS e clique em 'Iniciar câmera virtual'. " : "Ela pode estar em uso por outro programa. ") + "Se tiver outra câmera, escolha-a em Configurações > Câmera.";
      throw e;
    }
    const base = document.createElement("video");
    base.muted = true; base.playsInline = true; base.srcObject = camStream;
    await base.play().catch(() => {});

    const canvas = document.createElement("canvas");
    canvas.width = CFG.width; canvas.height = CFG.height;
    const g = canvas.getContext("2d", { alpha: false });
    const AC = window.AudioContext || window.webkitAudioContext;
    const ac = new AC();
    const dest = ac.createMediaStreamDestination();
    const micGain = ac.createGain();
    micGain.connect(dest);
    if (mic) {
      const micStream = await orig.gum({ audio: { deviceId: { exact: mic.deviceId }, echoCancellation: true, noiseSuppression: true } });
      ac.createMediaStreamSource(micStream).connect(micGain);
    }
    // O áudio do vídeo da marca tem caminho PRÓPRIO (não passa pelo cancelamento de eco/ruído do microfone)
    // e volume próprio. Os dois só se encontram no fim, porque a LIVE aceita uma única fonte de áudio.
    const clipGain = ac.createGain();
    clipGain.gain.value = CFG.clipVol;
    clipGain.connect(dest);

    function cover(src, sw, sh) {
      const r = Math.max(canvas.width / sw, canvas.height / sh);
      const w = sw * r, h = sh * r;
      g.drawImage(src, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    }
    function contain(src, sw, sh) {
      g.fillStyle = "#000"; g.fillRect(0, 0, canvas.width, canvas.height);
      const r = Math.min(canvas.width / sw, canvas.height / sh);
      const w = sw * r, h = sh * r;
      g.drawImage(src, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    }
    const timer = setInterval(() => {
      const c = S.clipEl;
      if (c && c.readyState >= 2 && c.videoWidth) contain(c, c.videoWidth, c.videoHeight);
      else if (base.videoWidth) cover(base, base.videoWidth, base.videoHeight);
    }, 1000 / CFG.fps);

    const vstream = canvas.captureStream(CFG.fps);
    return { ac, dest, micGain, clipGain, canvas, vstream, base, timer, cam: cam.label, mic: mic ? mic.label : "" };
  }

  function ensure() {
    if (S.built) return Promise.resolve(S.built);
    if (!S.building) S.building = build().then((b) => { S.built = b; S.lastError = ""; return b; }).finally(() => { S.building = null; });
    return S.building;
  }

  const ids = (c) => {
    const f = (v) => (v && typeof v === "object" ? v.exact || v.ideal : v);
    return { v: c && c.video ? (f(c.video.deviceId) || null) : null, a: c && c.audio ? (f(c.audio.deviceId) || null) : null };
  };
  const wantsLoopfy = (c) => {
    const { v, a } = ids(c);
    return (c && c.video && v === VCAM) || (c && c.audio && a === VMIC);
  };

  md.enumerateDevices = async () => {
    const list = await orig.enumerate();
    return list.concat([fakeInfo(VCAM, "videoinput", NAME_CAM), fakeInfo(VMIC, "audioinput", NAME_MIC)]);
  };

  md.getUserMedia = async (constraints) => {
    if (!constraints || !wantsLoopfy(constraints)) return orig.gum(constraints);
    const { v, a } = ids(constraints);
    const b = await ensure();
    const out = new MediaStream();
    if (constraints.video && v === VCAM) b.vstream.getVideoTracks().forEach((t) => out.addTrack(t.clone()));
    if (constraints.audio && a === VMIC) b.dest.stream.getAudioTracks().forEach((t) => out.addTrack(t.clone()));
    if (b.ac.state === "suspended") b.ac.resume().catch(() => {});
    return out;
  };

  /* ---- clipes da marca: só tocam por comando do operador, uma vez, sem loop ---- */
  function stopClip(reason) {
    const el = S.clipEl;
    S.clipEl = null; S.clip = null;
    if (el) { try { el.pause(); } catch (_) {} el.removeAttribute("src"); el.load(); }
    applyMic();
    S.status = reason || "idle";
  }

  async function play(id, name) {
    const b = await ensure();
    if (S.clipEl) stopClip("replaced");
    const el = document.createElement("video");
    el.crossOrigin = "anonymous";
    el.playsInline = true;
    el.loop = false; // nunca em loop
    el.src = `${CFG.clipHost}/c/${encodeURIComponent(id)}`;
    const src = b.ac.createMediaElementSource(el);
    src.connect(b.clipGain);
    // sequência: ao terminar, entra o próximo da fila; ao acabar a fila, volta para a câmera (sem repetir)
    el.addEventListener("ended", () => {
      if (S.queue.length && S.clipEl === el) { const n = S.queue.shift(); S.seqIndex += 1; play(n.id, n.name).catch(() => stopClip("error")); }
      else stopClip("ended");
    });
    el.addEventListener("error", () => { S.lastError = "erro ao carregar o clipe"; S.queue = []; stopClip("error"); });
    S.clipEl = el; S.clip = name || id; S.status = "playing";
    applyMic();
    if (b.ac.state === "suspended") await b.ac.resume().catch(() => {});
    await el.play();
    return true;
  }

  /* volumes: duck = nível do microfone enquanto um vídeo toca (0..1); clipVol = nível do áudio do vídeo (0..1) */
  function setLevels(duck, clipVol) {
    const clamp = (x, d) => (typeof x === "number" && isFinite(x) ? Math.min(1, Math.max(0, x)) : d);
    CFG.duck = clamp(duck, CFG.duck);
    CFG.clipVol = clamp(clipVol, CFG.clipVol);
    const b = S.built;
    if (!b) return;
    b.clipGain.gain.setTargetAtTime(CFG.clipVol, b.ac.currentTime, 0.05);
    applyMic();
  }

  function setMute(on) { S.mute = !!on; applyMic(); }

  /* sequência de vídeos da marca: toca uma vez, na ordem, e volta para a câmera. Só começa por comando do operador. */
  async function playSeq(list) {
    const items = (Array.isArray(list) ? list : []).filter((x) => x && x.id).slice(0, 30);
    if (!items.length) return false;
    S.queue = items.slice(1); S.seqTotal = items.length; S.seqIndex = 1;
    return play(items[0].id, items[0].name);
  }

  /* retorno: quadro pequeno do que está sendo enviado à LIVE (câmera ou vídeo da marca) */
  function frame() {
    const b = S.built;
    if (!b) return null;
    if (!S.prev) { S.prev = document.createElement("canvas"); S.prev.width = 360; S.prev.height = Math.round(360 * b.canvas.height / b.canvas.width); }
    S.prev.getContext("2d").drawImage(b.canvas, 0, 0, S.prev.width, S.prev.height);
    return S.prev.toDataURL("image/jpeg", 0.6);
  }

  window.__loopfy = {
    play: (id, name) => { S.queue = []; S.seqTotal = 1; S.seqIndex = 1; return play(id, name); },
    playSeq, stop: () => { S.queue = []; stopClip("stopped"); }, setLevels, setMute, frame,
    devices: async () => (await orig.enumerate()).filter((d) => !d.deviceId.startsWith("loopfy")).map((d) => d.kind + ": " + (d.label || "(sem nome)")),
    status: () => ({
      status: S.status, clip: S.clip, error: S.lastError, built: !!S.built, cam: S.built && S.built.cam, mic: S.built && S.built.mic, mute: S.mute, seq: { index: S.seqIndex, total: S.seqTotal },
      levels: S.built ? { mic: S.built.micGain.gain.value, clip: S.built.clipGain.gain.value } : null,
    }),
  };
})();
