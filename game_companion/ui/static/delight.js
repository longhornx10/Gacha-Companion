/* Delight: synthesized sounds (volume-controlled), copy buttons, and a
   currency "rain" celebration when a code is redeemed. No assets. */
(function () {
  "use strict";
  var KEY = "gc_sound_vol";
  // storage can throw (block-all-cookies, some private modes) — delight must
  // never take the page down with it
  function loadVol() {
    try { return parseInt(localStorage.getItem(KEY) || "30", 10); }
    catch (e) { return 30; }
  }
  function saveVol(v) {
    try { localStorage.setItem(KEY, String(v)); } catch (e) {}
  }
  var vol = loadVol();
  if (isNaN(vol)) vol = 30;

  var ctx = null;
  function audio() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function note(freq, start, dur, type, gain) {
    var ac = audio();
    if (!ac || vol <= 0) return;
    var osc = ac.createOscillator();
    var amp = ac.createGain();
    osc.type = type || "sine";
    osc.frequency.value = freq;
    var v = (gain == null ? 0.5 : gain) * (vol / 100) * 0.25;
    amp.gain.setValueAtTime(0.0001, ac.currentTime + start);
    amp.gain.exponentialRampToValueAtTime(v, ac.currentTime + start + 0.015);
    amp.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + start + dur);
    osc.connect(amp).connect(ac.destination);
    osc.start(ac.currentTime + start);
    osc.stop(ac.currentTime + start + dur + 0.05);
  }

  var sounds = {
    tick: function () { note(880, 0, 0.07, "sine", 0.4); },
    pop: function () { note(320, 0, 0.09, "square", 0.28); note(720, 0.05, 0.12, "sine", 0.45); },
    chime: function () { note(660, 0, 0.16, "sine", 0.5); note(990, 0.09, 0.22, "sine", 0.4); },
    sparkle: function () {
      note(523, 0, 0.14, "triangle", 0.5);
      note(659, 0.09, 0.14, "triangle", 0.5);
      note(784, 0.18, 0.14, "triangle", 0.5);
      note(1047, 0.27, 0.3, "triangle", 0.55);
    },
  };

  window.gcSound = {
    volume: function () { return vol; },
    setVolume: function (v) {
      vol = Math.max(0, Math.min(100, parseInt(v, 10) || 0));
      saveVol(vol);
    },
    play: function (name) { if (sounds[name]) sounds[name](); },
  };

  /* ---- currency rain ------------------------------------------------ */
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function shade(hex, amt) {
    var n = parseInt(hex.slice(1), 16);
    var r = Math.min(255, Math.max(0, (n >> 16) + amt));
    var g = Math.min(255, Math.max(0, ((n >> 8) & 255) + amt));
    var b = Math.min(255, Math.max(0, (n & 255) + amt));
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  function drawCrystal(g, s) {
    // iridescent polychrome-style shard: elongated faceted hexagon
    var grad = g.createLinearGradient(-s, -s, s, s);
    grad.addColorStop(0, "#b16cff");
    grad.addColorStop(0.55, "#7a5cff");
    grad.addColorStop(1, "#41d1ff");
    g.fillStyle = grad;
    g.beginPath();
    g.moveTo(0, -s * 1.35);
    g.lineTo(s * 0.72, -s * 0.45);
    g.lineTo(s * 0.5, s);
    g.lineTo(0, s * 1.3);
    g.lineTo(-s * 0.5, s);
    g.lineTo(-s * 0.72, -s * 0.45);
    g.closePath();
    g.fill();
    g.strokeStyle = "rgba(255,255,255,0.55)";
    g.lineWidth = Math.max(0.6, s * 0.09);
    g.beginPath();
    g.moveTo(0, -s * 1.35);
    g.lineTo(0, s * 1.3);
    g.moveTo(-s * 0.72, -s * 0.45);
    g.lineTo(s * 0.72, -s * 0.45);
    g.stroke();
  }

  function drawHexCoin(g, s, color) {
    g.fillStyle = color;
    g.beginPath();
    for (var i = 0; i < 6; i++) {
      var a = (Math.PI / 3) * i - Math.PI / 2;
      var x = Math.cos(a) * s, y = Math.sin(a) * s;
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.closePath();
    g.fill();
    g.strokeStyle = shade(color, 70);
    g.lineWidth = Math.max(0.8, s * 0.16);
    g.beginPath();
    g.arc(0, 0, s * 0.5, 0, Math.PI * 2);
    g.stroke();
  }

  function drawJade(g, s) {
    // stellar-jade-style rounded diamond gem
    var grad = g.createLinearGradient(-s, -s, s, s);
    grad.addColorStop(0, "#bfe8d2");
    grad.addColorStop(0.5, "#5fd4a0");
    grad.addColorStop(1, "#2e8f6b");
    g.fillStyle = grad;
    g.beginPath();
    g.moveTo(0, -s * 1.2);
    g.lineTo(s, 0);
    g.lineTo(0, s * 1.2);
    g.lineTo(-s, 0);
    g.closePath();
    g.fill();
    g.strokeStyle = "rgba(255,255,255,0.6)";
    g.lineWidth = Math.max(0.6, s * 0.1);
    g.beginPath();
    g.moveTo(-s * 0.4, -s * 0.3);
    g.lineTo(0, -s * 0.8);
    g.stroke();
  }

  function currencyRain() {
    if (reduce) return;
    var shape = document.body.getAttribute("data-currency-shape") || "pieces";
    var iconUrl = document.body.getAttribute("data-currency-icon") || "";
    var colors = (document.body.getAttribute("data-currency-colors") || "").split(",").filter(Boolean);
    if (!colors.length) colors = ["#ffd24a", "#b16cff", "#41d1ff"];
    var icon = null;
    if (iconUrl) {
      try {
        icon = new Image();
        icon.src = iconUrl;
      } catch (e) { icon = null; }
    }
    var canvas = document.createElement("canvas");
    canvas.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:99;";
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);
    var g = canvas.getContext("2d");
    var parts = [];
    for (var i = 0; i < 80; i++) {
      parts.push({
        x: Math.random() * canvas.width,
        y: -24 - Math.random() * canvas.height * 0.5,
        vy: 2.6 + Math.random() * 3.4,
        sway: 0.6 + Math.random() * 1.6,
        phase: Math.random() * Math.PI * 2,
        s: 6 + Math.random() * 7,
        rot: Math.random() * Math.PI,
        vr: (Math.random() - 0.5) * 0.18,
        color: colors[i % colors.length],
      });
    }
    var start = performance.now();
    function frame(now) {
      var t = (now - start) / 1000;
      g.clearRect(0, 0, canvas.width, canvas.height);
      g.globalAlpha = Math.max(0, 1 - Math.max(0, t - 0.95) / 0.5);
      parts.forEach(function (p) {
        p.y += p.vy;
        p.x += Math.sin(t * 3 + p.phase) * p.sway * 0.6;
        p.rot += p.vr;
        g.save();
        g.translate(p.x, p.y);
        g.rotate(Math.sin(t * 2.2 + p.phase) * 0.5);
        if (shape === "crystal") drawCrystal(g, p.s);
        else if (shape === "hex") drawHexCoin(g, p.s, p.color);
        else if (shape === "image" && icon && icon.complete && icon.naturalWidth) {
          var w = p.s * 1.9;
          g.drawImage(icon, -w / 2, -w / 2, w, w);
        } else if (shape === "image") drawJade(g, p.s);
        else {
          g.fillStyle = p.color;
          g.fillRect(-p.s / 2, -p.s / 2, p.s, p.s * 1.4);
        }
        g.restore();
      });
      if (t < 1.5) requestAnimationFrame(frame);
      else canvas.remove();
    }
    requestAnimationFrame(frame);
  }
  window.gcConfetti = currencyRain;

  /* ---- full-size image preview (banner art, portraits) ----------------- */
  function openLightbox(src, alt) {
    var box = document.createElement("div");
    box.className = "gc-lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", alt || "Full size image");
    var img = document.createElement("img");
    img.src = src;
    img.alt = alt || "";
    var close = document.createElement("button");
    close.className = "lb-close";
    close.type = "button";
    close.setAttribute("aria-label", "Close preview");
    close.textContent = "✕";
    box.appendChild(img);
    box.appendChild(close);
    document.body.appendChild(box);
    var shut = function () { box.remove(); document.removeEventListener("keydown", onKey); };
    var onKey = function (e) { if (e.key === "Escape") shut(); };
    document.addEventListener("keydown", onKey);
    box.addEventListener("click", function (e) {
      if (e.target === box || e.target === close || e.target === img) shut();
    });
    close.focus();
  }
  window.gcLightbox = openLightbox;
  document.addEventListener("click", function (e) {
    var img = e.target.closest && e.target.closest("img[data-lightbox]");
    if (!img) return;
    e.preventDefault();
    openLightbox(img.getAttribute("data-lightbox") || img.src, img.alt);
  });

  /* destructive-action confirmations: forms opt in with data-confirm="…" */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof Element) || !form.hasAttribute("data-confirm")) return;
    if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
  }, true);

  /* ---- page wiring --------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", function () {
    var slider = document.getElementById("sound-vol");
    if (slider) {
      slider.value = vol;
      var label = document.getElementById("sound-vol-label");
      if (label) label.textContent = vol + "%";
      slider.addEventListener("input", function () {
        window.gcSound.setVolume(slider.value);
        if (label) label.textContent = slider.value + "%";
      });
      slider.addEventListener("change", function () { sounds.chime(); });
      var test = document.getElementById("sound-test");
      if (test) test.addEventListener("click", function () { sounds.sparkle(); });
    }

    // copy buttons on code cards
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        var done = function () {
          sounds.pop();
          var old = btn.textContent;
          btn.textContent = "Copied!";
          setTimeout(function () { btn.textContent = old; }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, done);
        } else {
          var ta = document.createElement("textarea");
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand("copy"); } catch (e) {}
          ta.remove();
          done();
        }
      });
    });

    // celebration when a code was redeemed (notice text from the server)
    var notice = document.querySelector(".notice");
    if (notice && /redeemed/i.test(notice.textContent)) {
      sounds.pop();
      currencyRain();
    } else if (notice) {
      sounds.tick();
    }

    // achievement toast
    var toast = document.querySelector("[data-sound]");
    if (toast) {
      if (!reduce) sounds[toast.getAttribute("data-sound")]();
      setTimeout(function () { toast.remove(); }, 6500);
    }
  });
})();
