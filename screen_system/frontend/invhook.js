/* invhook.js — 在庫QRシリアルをどの画面でも消尽できる共有フック
 *   使い方: <script src="/static/invhook.js"></script> を読み込み、
 *           各画面のスキャン処理の先頭に一行:
 *             if (window.InvScan && InvScan.isSerial(code)) { InvScan.consume(code); return; }
 *   在庫シリアル(例 11-00001)なら /api/inventory/scan で -1(消尽)し、
 *   画面右上にトーストで結果を表示する。生産バーコード(CDI...)は素通り。
 */
(function () {
  // 在庫シリアル: 「2〜4桁 - 3〜6桁」 例) 11-00001 。生産バーコード(英字始まり)とは衝突しない。
  var PAT = /^\d{2,4}-\d{3,6}$/;

  function ensureUI() {
    if (document.getElementById("invhook-wrap")) return;
    var st = document.createElement("style");
    st.textContent =
      '#invhook-wrap{position:fixed;top:16px;right:16px;z-index:99999;display:flex;flex-direction:column;gap:10px;' +
      'font-family:"Yu Gothic","Hiragino Kaku Gothic ProN","Noto Sans JP",Arial,sans-serif;pointer-events:none;}' +
      '.invhook-toast{min-width:260px;max-width:380px;padding:14px 16px;border-radius:12px;color:#fff;' +
      'box-shadow:0 8px 26px rgba(0,0,0,.32);animation:invhookIn .16s ease;}' +
      '.invhook-toast.ok{background:#12a45a;border:1px solid #0c7a43;}' +
      '.invhook-toast.ng{background:#c0392b;border:1px solid #922b21;}' +
      '.invhook-toast .h{font-size:20px;font-weight:900;margin-bottom:2px;}' +
      '.invhook-toast .n{font-size:17px;font-weight:800;}' +
      '.invhook-toast .m{font-size:13px;opacity:.92;margin-top:2px;font-family:"Consolas",monospace;}' +
      '.invhook-toast .low{display:inline-block;margin-top:6px;background:#fff;color:#c0392b;font-weight:900;' +
      'font-size:12px;padding:2px 8px;border-radius:999px;}' +
      '@keyframes invhookIn{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}';
    document.head.appendChild(st);
    var w = document.createElement("div");
    w.id = "invhook-wrap";
    document.body.appendChild(w);
  }

  function toast(ok, html, ms) {
    ensureUI();
    var el = document.createElement("div");
    el.className = "invhook-toast " + (ok ? "ok" : "ng");
    el.innerHTML = html;
    document.getElementById("invhook-wrap").appendChild(el);
    setTimeout(function () {
      el.style.transition = "opacity .3s";
      el.style.opacity = "0";
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, ms || (ok ? 2600 : 3800));
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c];
    });
  }

  async function consume(code, opts) {
    opts = opts || {};
    code = (code || "").trim();
    try {
      var res = await fetch("/api/inventory/scan", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code, worker: opts.worker || null })
      });
      var d = await res.json();
      if (d.ok) {
        toast(true,
          '<div class="h">✓ 在庫 −1 ' + esc(d.unit || "") + '</div>' +
          '<div class="n">' + esc(d.name || "") + '</div>' +
          '<div class="m">' + esc(d.serial || code) + ' / 残り ' + esc(d.balance) + ' ' + esc(d.unit || "") + '</div>' +
          (d.low ? '<span class="low">要発注</span>' : ''));
      } else {
        toast(false,
          '<div class="h">✕ ' + esc(d.reason || "エラー") + '</div>' +
          '<div class="m">' + esc(d.serial || code) + '</div>');
      }
      if (typeof opts.onDone === "function") opts.onDone(d);
      return d;
    } catch (e) {
      toast(false, '<div class="h">✕ 通信エラー</div><div class="m">' + esc((e && e.message) || e) + '</div>');
      return { ok: false, reason: "network" };
    }
  }

  window.InvScan = {
    isSerial: function (code) { return PAT.test((code || "").trim()); },
    consume: consume
  };
})();
