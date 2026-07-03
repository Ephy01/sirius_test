(function () {
  "use strict";
  var KEY = "delivergo"; 
  var scenario = null, session = null, nodeEnterTime = 0, advisorState = null, theoryOpenedPre = false;
  var app = document.getElementById("app");

  function optById(id) {
    var found = null;
    Object.keys(scenario.nodes).forEach(function (nid) {
      (scenario.nodes[nid].options || []).forEach(function (o) { if (o.id === id) found = o; });
    });
    return found;
  }
  function kpiMeta(key) { return scenario.meta.kpis.filter(function (k) { return k.key === key; })[0]; }
  function fmt(key, v) {
    var m = kpiMeta(key);
    if (!m) return v;
    if (m.format === "percent") return v + "%";
    if (m.format === "rub") return v.toLocaleString("ru-RU") + " \u20bd";
    return "" + v;
  }
  function deltaClass(key, dv) {
    if (dv === 0) return "flat";
    var m = kpiMeta(key);
    if (m && m.goal === "min") return dv < 0 ? "up" : "down";
    if (m && m.goal === "band") return "flat";
    return dv > 0 ? "up" : "down";
  }
  function esc(s) {
    return (s || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function choiceStages() {
    return Object.keys(scenario.nodes).filter(function (k) { return scenario.nodes[k].type === "choice"; });
  }
  function decidedMap() {
    var d = {};
    session.log.forEach(function (r) { if (r.type === "choice") d[r.node] = r.choiceQuality; });
    return d;
  }
  function starCount() {
    return session.log.filter(function (r) { return r.type === "choice" && r.choiceQuality === "good"; }).length;
  }

  
  function newSession() {
    session = {
      sessionId: "s_" + Date.now().toString(36), startedAt: Date.now(), finishedAt: null,
      state: JSON.parse(JSON.stringify(scenario.meta.initial_state)),
      currentNode: scenario.meta.start_node, history: [scenario.meta.start_node], log: [], done: false,
    };
    save();
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(session)); } catch (e) {} }
  function loadSession() {
    try { var raw = localStorage.getItem(KEY); if (raw) { session = JSON.parse(raw); return true; } }
    catch (e) {}
    return false;
  }

  
  function stepBar() {
    var stages = choiceStages(), dec = decidedMap(), cur = session.currentNode;
    var cells = stages.map(function (id, i) {
      var st = dec[id] || (id === cur ? "current" : "upcoming");
      var ic = dec[id] ? (st === "bad" ? "\u2715" : (st === "warn" ? "\u26a0" : "\u2713"))
                       : (st === "current" ? "\u25b6" : (i + 1));
      return '<div class="step s-' + st + '" title="' + esc(scenario.nodes[id].title) + '">' + ic + "</div>";
    }).join("");
    return '<div class="stepwrap">' + cells + "</div>";
  }
  function kpiStrip() {
    var cells = scenario.meta.kpis.map(function (m) {
      var v = session.state[m.key], crit = m.critical_below != null && v < m.critical_below;
      return '<div class="kchip ' + (crit ? "crit" : "") + '"><span class="kl">' + m.label +
        '</span><span class="kv">' + fmt(m.key, v) + "</span></div>";
    }).join("");
    return '<div class="kpistrip">' + cells + "</div>";
  }

  
  function journeyMap() {
    var stages = choiceStages(), dec = decidedMap();
    var W = 680, mx = 54, topY = 56, rowH = 120, cols = 6, r = 17;
    var rows = Math.ceil(stages.length / cols), colW = (W - 2 * mx) / (cols - 1);
    var pos = stages.map(function (id, i) {
      var row = Math.floor(i / cols), p = i % cols;
      var x = row % 2 === 0 ? mx + p * colW : mx + (cols - 1 - p) * colW;
      return { id: id, x: x, y: topY + row * rowH, q: dec[id] || "upcoming" };
    });
    var H = topY + (rows - 1) * rowH + 74;
    var color = { good: "#3fbf6a", warn: "#f5b93b", bad: "#ef5f5f", upcoming: "#3a4059", current: "#7a2fe4" };
    var GF = "'Golos Text',sans-serif";
    var conn = "";
    for (var i = 0; i < pos.length - 1; i++) {
      var a = pos[i], b = pos[i + 1], d;
      if (Math.abs(a.y - b.y) < 8) { var m2 = (a.x + b.x) / 2; d = "M" + a.x + " " + a.y + " C " + m2 + " " + a.y + ", " + m2 + " " + b.y + ", " + b.x + " " + b.y; }
      else { var bow = 48; d = "M" + a.x + " " + a.y + " C " + (a.x + bow) + " " + (a.y + bow * 0.6) + ", " + (b.x + bow) + " " + (b.y - bow * 0.6) + ", " + b.x + " " + b.y; }
      conn += '<path d="' + d + '" fill="none" stroke="#333a52" stroke-width="3" stroke-linecap="round"/>';
    }
    var branch = "";
    if (session.history.indexOf("s2_recovery") >= 0) {
      var s2 = pos[1], bx = s2.x - 6, by = s2.y + 58;
      branch = '<path d="M' + s2.x + " " + s2.y + " C " + (s2.x - 30) + " " + (s2.y + 26) + ", " + (bx - 24) + " " + (by - 20) + ", " + bx + " " + by + '" fill="none" stroke="#5b4a2a" stroke-width="2.5" stroke-dasharray="4 4"/>' +
        '<circle cx="' + bx + '" cy="' + by + '" r="11" fill="#5b4633" stroke="#f5b93b" stroke-width="1.5"/>' +
        '<text x="' + bx + '" y="' + (by + 4) + '" text-anchor="middle" font-size="11" fill="#f5d38b" font-family="' + GF + '">\u21ba</text>' +
        '<text x="' + bx + '" y="' + (by + 26) + '" text-anchor="middle" font-size="9.5" fill="#8b93a6" font-family="' + GF + '">\u043e\u0442\u043a\u0430\u0442</text>';
    }
    var pins = "";
    pos.forEach(function (pp, i) {
      var c = color[pp.q] || color.upcoming;
      var tail = "M" + (pp.x - 6) + " " + (pp.y + r - 3) + " L" + (pp.x + 6) + " " + (pp.y + r - 3) + " L" + pp.x + " " + (pp.y + r + 9) + " Z";
      pins += "<g><title>" + esc(scenario.nodes[pp.id].title) + "</title>" +
        '<path d="' + tail + '" fill="' + c + '"/>' +
        '<circle cx="' + pp.x + '" cy="' + pp.y + '" r="' + r + '" fill="' + c + '"/>' +
        '<text x="' + pp.x + '" y="' + (pp.y + 5) + '" text-anchor="middle" font-size="13" font-weight="700" fill="#fff" font-family="' + GF + '">' + (i + 1) + "</text>" +
        '<text x="' + pp.x + '" y="' + (pp.y + r + 26) + '" text-anchor="middle" font-size="10.5" fill="#aeb6c9" font-family="' + GF + '">' + esc(scenario.nodes[pp.id].time) + "</text></g>";
    });
    return '<svg class="journey" viewBox="0 0 ' + W + " " + H + '" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="\u041a\u0430\u0440\u0442\u0430 \u043f\u0443\u0442\u0438">' + conn + branch + pins + "</svg>";
  }

  
  function shell(inner, opts) {
    opts = opts || {};
    var header = '<header class="topbar"><div class="brand"><div class="logo">' +
      "<i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>" +
      '<div class="bname">DeliverGo <span>\u00b7 \u0421\u043b\u043e\u043c\u0430\u043d\u043d\u044b\u0439 \u0434\u0435\u043d\u044c</span></div></div>' +
      '<div class="hactions"><div class="stars"><span class="st">\u2605</span>' + starCount() + '/' + choiceStages().length + '</div>' +
      '<button class="ghost" id="reset">\u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e</button></div></header>';
    app.innerHTML = header + (opts.steps ? stepBar() : "") + (opts.kpis ? kpiStrip() : "") +
      '<main class="stage">' + inner + "</main>";
    var rst = document.getElementById("reset");
    if (rst) rst.onclick = function () {
      if (confirm("\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u0440\u043e\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435 \u0438 \u043e\u0447\u0438\u0441\u0442\u0438\u0442\u044c localStorage?")) { newSession(); render(); }
    };
  }

  function render() {
    var node = scenario.nodes[session.currentNode];
    advisorState = null; nodeEnterTime = Date.now(); theoryOpenedPre = false;
    if (session.done || node.type === "final") return renderFinal();
    if (node.type === "info") return renderInfo(node);
    if (node.type === "choice") return renderChoice(node);
  }

  function renderInfo(node) {
    var body = esc(node.body).replace(/\n/g, "<br>");
    if (session.currentNode === "intro") {
      var chips = '<div class="metachips"><span>3 \u043a\u0443\u0445\u043d\u0438</span><span>12 \u043a\u0443\u0440\u044c\u0435\u0440\u043e\u0432</span>' +
        '<span>13 \u0440\u0435\u0448\u0435\u043d\u0438\u0439</span><span>\u0418\u0418-\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a \u043d\u0430 6 \u0440\u0430\u0437\u0432\u0438\u043b\u043a\u0430\u0445</span></div>';
      var assess = '<details class="assess"><summary>\u041a\u0430\u043a \u043e\u0446\u0435\u043d\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u043f\u0440\u043e\u0445\u043e\u0436\u0434\u0435\u043d\u0438\u0435</summary>' +
        '<ul>' +
        '<li><b>\u041f\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0437\u0430\u043f\u0440\u043e\u0441\u0430</b> \u2014 \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u0443\u0435\u0442\u0435 \u043b\u0438 \u0432\u044b \u0418\u0418 \u0437\u0430\u0434\u0430\u0447\u0443 \u0441 \u0446\u0435\u043b\u044c\u044e \u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f\u043c\u0438.</li>' +
        '<li><b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0439</b> \u2014 \u043d\u0430\u0445\u043e\u0434\u0438\u0442\u0435 \u043b\u0438 \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u044f \u0432 \u0440\u0430\u0441\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u044f\u0445 \u0418\u0418 (\u0441\u043e\u0432\u0435\u0442\u044b \u043c\u043e\u0433\u0443\u0442 \u0431\u044b\u0442\u044c \u043e\u0448\u0438\u0431\u043e\u0447\u043d\u044b\u043c\u0438, \u043a\u0430\u043a \u0438 \u0432 \u0436\u0438\u0437\u043d\u0438).</li>' +
        '<li><b>\u041a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0430 \u043e\u043f\u043e\u0440\u044b</b> \u2014 \u0441\u043b\u0435\u0434\u0443\u0435\u0442\u0435 \u043b\u0438 \u0445\u043e\u0440\u043e\u0448\u0438\u043c \u0441\u043e\u0432\u0435\u0442\u0430\u043c \u0438 \u043e\u0442\u043a\u043b\u043e\u043d\u044f\u0435\u0442\u0435 \u043b\u0438 \u043f\u043b\u043e\u0445\u0438\u0435.</li>' +
        '<li><b>\u041e\u0431\u0443\u0447\u0430\u0435\u043c\u043e\u0441\u0442\u044c</b> \u2014 \u0443\u043b\u0443\u0447\u0448\u0430\u044e\u0442\u0441\u044f \u043b\u0438 \u0440\u0435\u0448\u0435\u043d\u0438\u044f \u043f\u043e \u0445\u043e\u0434\u0443 \u0434\u043d\u044f.</li>' +
        '<li><b>\u041f\u0435\u0440\u0435\u043d\u043e\u0441 \u043f\u0440\u0438\u043d\u0446\u0438\u043f\u043e\u0432</b> \u2014 \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0435\u0442\u0435 \u043b\u0438 \u0443\u0441\u0432\u043e\u0435\u043d\u043d\u043e\u0435 \u0432 \u043d\u043e\u0432\u044b\u0445 \u0441\u0438\u0442\u0443\u0430\u0446\u0438\u044f\u0445, \u0432 \u0442\u043e\u043c \u0447\u0438\u0441\u043b\u0435 \u0431\u0435\u0437 \u0418\u0418.</li>' +
        '</ul><p>\u041e\u0446\u0435\u043d\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u043f\u0440\u043e\u0446\u0435\u0441\u0441, \u0430 \u043d\u0435 \u0442\u043e\u043b\u044c\u043a\u043e \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 P&amp;L. \u0412\u0441\u0435 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u044f \u043a \u0418\u0418 \u043b\u043e\u0433\u0438\u0440\u0443\u044e\u0442\u0441\u044f; \u0441\u044b\u0440\u043e\u0439 \u043b\u043e\u0433 \u0441\u0435\u0441\u0441\u0438\u0438 \u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0432\u0430\u043c \u043d\u0430 \u0444\u0438\u043d\u0430\u043b\u044c\u043d\u043e\u043c \u044d\u043a\u0440\u0430\u043d\u0435, \u0430 \u0440\u0430\u0441\u0447\u0451\u0442 \u043c\u0435\u0442\u0440\u0438\u043a \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u043d\u0430 \u0441\u0442\u043e\u0440\u043e\u043d\u0435 \u0438\u0441\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u0438 \u0432 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0435 \u043d\u0435 \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0430\u0435\u0442\u0441\u044f.</p></details>';
      var html = '<section class="hero"><div class="time">\u0421\u0418\u041c\u0423\u041b\u042f\u0426\u0418\u042f \u00b7 \u041e\u041f\u0415\u0420\u0410\u0426\u0418\u041e\u041d\u041d\u042b\u0419 \u0414\u0415\u041d\u042c</div>' +
        "<h1>" + esc(node.title) + "</h1>" +
        (node.subtitle ? '<p class="sub">' + esc(node.subtitle) + "</p>" : "") +
        '<p class="body">' + body + "</p>" + chips + assess +
        '<button class="cta-white" id="go">\u041d\u0430\u0447\u0430\u0442\u044c \u0434\u0435\u043d\u044c \u25b6</button></section>';
      shell(html, {});
    } else {
      var h2 = '<section class="card">' + (node.time ? '<div class="time">' + node.time + "</div>" : "") +
        "<h1>" + esc(node.title) + '</h1><p class="body">' + body + "</p>" +
        '<button class="primary" id="go">\u0414\u0430\u043b\u0435\u0435 \u25b6</button></section>';
      shell(h2, { steps: true, kpis: true });
    }
    document.getElementById("go").onclick = function () {
      session.currentNode = node.next; session.history.push(node.next); save(); render();
    };
  }

  function openTheory(node) {
    if (!node.theory) return;
    theoryOpenedPre = true;
    var ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = '<div class="fbcard theory-card">' +
      '<div class="fbtop"><span class="qbadge">📖</span><span class="fbtitle">' + esc(node.theory.principle) + "</span></div>" +
      '<div class="fbbody"><p class="fbtext">' + esc(node.theory.detail) + "</p>" +
      '<div class="fbactions"><button class="primary" id="thclose">Понятно</button></div></div></div>';
    app.appendChild(ov);
    document.getElementById("thclose").onclick = function () { ov.remove(); };
  }

  function renderChoice(node) {
    var opts = node.options.map(function (o, i) {
      return '<button class="opt"' + (node.advisor ? " disabled" : "") + ' data-oid="' + o.id + '">' +
        '<div class="ol"><span class="oi">' + (i + 1) + '</span><span class="ott">' + esc(o.label) + "</span></div>" +
        '<div class="od">' + esc(o.desc) + "</div></button>";
    }).join("");

    var advBlock = "";
    if (node.advisor) {
      advBlock = '<div class="advisor" id="advisor"><div class="ahd">' +
        '<span class="chip">\u0418\u0418-\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0439</span>' +
        '<span class="ahint">\u0441\u043e\u0432\u0435\u0449\u0430\u0442\u0435\u043b\u044c\u043d\u043e \u00b7 \u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u0437\u0430 \u0432\u0430\u043c\u0438</span></div>' +
        '<div class="astep">\u0428\u0430\u0433 1. \u0412\u0430\u0448\u0435 \u043f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u2014 \u0434\u043e \u0441\u043e\u0432\u0435\u0442\u0430 \u0438 \u0431\u0435\u0437 \u043d\u0435\u0433\u043e</div>' +
        '<div class="lean" id="lean">' +
        node.options.map(function (o, i) {
          return '<label class="leanopt"><input type="radio" name="lean" value="' + o.id + '"> ' + (i + 1) + ". " + esc(o.label) + "</label>";
        }).join("") + "</div>" +
        '<button class="lockbtn" id="lockIntent" disabled>\u0417\u0430\u0444\u0438\u043a\u0441\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043d\u0430\u043c\u0435\u0440\u0435\u043d\u0438\u0435</button>' +
        '<div class="astep">\u0428\u0430\u0433 2. \u0421\u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u0443\u0439\u0442\u0435 \u0437\u0430\u043f\u0440\u043e\u0441 \u043c\u043e\u0434\u0435\u043b\u0438 <span class="gatenote">(\u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u043f\u043e\u0441\u043b\u0435 \u0444\u0438\u043a\u0441\u0430\u0446\u0438\u0438 \u043d\u0430\u043c\u0435\u0440\u0435\u043d\u0438\u044f \u00b7 \u043e\u0434\u043d\u043e \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435)</span></div>' +
        '<textarea id="prompt" rows="2" disabled placeholder="\u041d\u0430\u043f\u0440.: \u043f\u0440\u0438 \u043e\u0447\u0435\u0440\u0435\u0434\u0438 4 \u0438 \u043a\u043e\u043c\u0430\u043d\u0434\u0435 45% \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0438 \u0432\u0430\u0440\u0438\u0430\u043d\u0442, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u0437\u0430\u0449\u0438\u0442\u0438\u0442 SLA \u0431\u0435\u0437 \u0432\u044b\u0433\u043e\u0440\u0430\u043d\u0438\u044f, \u0438 \u0443\u043a\u0430\u0436\u0438 \u0440\u0438\u0441\u043a\u0438"></textarea>' +
        '<button class="ai" id="askAI" disabled>\u25b7 \u0421\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u0418\u0418-\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430</button>' +
        '<div id="aiOut"></div></div>';
    }
    var lead = node.advisor
      ? '<p class="hintline" id="optHint">\u0418\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u0432\u044b\u0431\u043e\u0440 \u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u043f\u043e\u0441\u043b\u0435 \u0442\u043e\u0433\u043e, \u043a\u0430\u043a \u0432\u044b \u0437\u0430\u0444\u0438\u043a\u0441\u0438\u0440\u0443\u0435\u0442\u0435 \u043f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435. \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0435\u0433\u043e \u043f\u043e\u0442\u043e\u043c \u043d\u0435\u043b\u044c\u0437\u044f \u2014 \u043d\u043e \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u0432\u044b\u0431\u043e\u0440 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043b\u044e\u0431\u044b\u043c.</p>'
      : "";
    var theoryBtn = node.theory
      ? '<button class="ghost tbtn" id="theoryBtn">\ud83d\udcd6 \u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u0442\u0435\u043e\u0440\u0438\u044e</button>' : "";
    var html = '<section class="card"><div class="time">' + node.time + "</div>" +
      "<h1>" + esc(node.title) + '</h1><p class="body">' + esc(node.body).replace(/\n/g, "<br>") + "</p>" +
      advBlock + lead +
      '<div class="choose">\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435' + (node.advisor ? " (\u0438\u0442\u043e\u0433)" : "") + ":</div>" +
      '<div class="opts" id="opts">' + opts + "</div>" + theoryBtn + "</section>";
    shell(html, { steps: true, kpis: true });
    var tb = document.getElementById("theoryBtn");
    if (tb) tb.onclick = function () { openTheory(node); };
    if (node.advisor) wireAdvisor(node);
    wireOptions(node);
  }

  function wireAdvisor(node) {
    advisorState = { prediction: null, intentAt: null, prompt: null, promptScore: null, promptRelevant: null,
            advice: null, verified: false, judgment: null, asked: false };
    var lean = document.getElementById("lean"), promptEl = document.getElementById("prompt"),
        askBtn = document.getElementById("askAI"), lockBtn = document.getElementById("lockIntent");
    lean.addEventListener("change", function (e) {
      if (advisorState.intentAt) return;
      advisorState.prediction = e.target.value; lockBtn.disabled = false;
    });
    lockBtn.onclick = function () {
      if (!advisorState.prediction || advisorState.intentAt) return;
      advisorState.intentAt = Date.now();
      app.querySelectorAll("#lean input").forEach(function (r) { r.disabled = true; });
      lockBtn.disabled = true; lockBtn.textContent = "✓ Намерение зафиксировано";
      promptEl.disabled = false; askBtn.disabled = false;
      app.querySelectorAll(".opt").forEach(function (b) { b.disabled = false; });
      var oh = document.getElementById("optHint");
      if (oh) oh.textContent = "Намерение записано. Теперь можно спросить ИИ-аналитика — или принять итоговое решение без него.";
    };
    askBtn.onclick = function () {
      if (!advisorState.intentAt || advisorState.asked) return;
      var ps = AIAdvisor.scorePrompt(promptEl.value);
      advisorState.prompt = promptEl.value; advisorState.promptScore = ps.score; advisorState.promptRelevant = ps.relevant;
      advisorState.advice = AIAdvisor.getAdvice(node.id, session.state); advisorState.asked = true;
      var rec = optById(advisorState.advice.recommend);
      var pred = scenario.meta.kpis.map(function (m) {
        var dv = advisorState.advice.predicted[m.key] || 0;
        return '<span class="pk ' + deltaClass(m.key, dv) + '">' + m.label + " " + (dv > 0 ? "+" : "") + dv + "</span>";
      }).join("");
      var relNote = ps.relevant
        ? '<span class="okrel">\u0437\u0430\u043f\u0440\u043e\u0441 \u0440\u0435\u043b\u0435\u0432\u0430\u043d\u0442\u0435\u043d \u00b7 \u043e\u0446\u0435\u043d\u043a\u0430 \u043f\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438 ' + ps.score + "/4</span>"
        : '<span class="badrel">\u26a0 \u0437\u0430\u043f\u0440\u043e\u0441 \u0432\u043d\u0435 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430 \u0437\u0430\u0434\u0430\u0447\u0438 (\u0441\u0435\u043c\u0430\u043d\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0444\u0438\u043b\u044c\u0442\u0440) \u00b7 \u043e\u0446\u0435\u043d\u043a\u0430 0/4</span>';
      document.getElementById("aiOut").innerHTML = '<div class="aicard">' +
        '<div class="relrow">' + relNote + "</div>" +
        '<div class="aihead">\ud83e\udd16 ' + esc(advisorState.advice.headline) + "</div>" +
        '<div class="airec">\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0435\u0442: <b>' + esc(rec ? rec.label : advisorState.advice.recommend) + "</b></div>" +
        '<div class="aipred">\u041f\u0440\u043e\u0433\u043d\u043e\u0437 \u043c\u043e\u0434\u0435\u043b\u0438: ' + pred + "</div>" +
        '<button class="verify" id="verify">\ud83d\udd0d \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435</button><div id="verifyOut"></div></div>';
      askBtn.disabled = true; promptEl.disabled = true;
      askBtn.textContent = "\u2713 \u0421\u043e\u0432\u0435\u0442 \u043f\u043e\u043b\u0443\u0447\u0435\u043d (\u043e\u0434\u043d\u043e \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435 \u043d\u0430 \u0440\u0430\u0437\u0432\u0438\u043b\u043a\u0443)";
      document.getElementById("verify").onclick = function () {
        advisorState.verified = true;
        document.getElementById("verifyOut").innerHTML =
          '<div class="reason"><div class="rl">\u0420\u0430\u0441\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u0438:</div>' + esc(advisorState.advice.reasoning) + "</div>" +
          '<div class="judge" id="judge"><div class="rl">\u0412\u0430\u0448 \u0432\u0435\u0440\u0434\u0438\u043a\u0442 (\u0441\u0432\u0435\u0440\u044c\u0442\u0435 \u0440\u0430\u0441\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u0435 \u0441 \u043f\u0440\u043e\u0433\u043d\u043e\u0437\u043e\u043c \u0438 \u0441\u0438\u0442\u0443\u0430\u0446\u0438\u0435\u0439):</div>' +
          '<button class="jbtn" data-j="sound">\u2713 \u041e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0432\u044b\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443</button>' +
          '<button class="jbtn" data-j="flawed">\u26a0 \u0412 \u0441\u043e\u0432\u0435\u0442\u0435 \u0435\u0441\u0442\u044c \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0435</button>' +
          '<div class="jnote" id="jnote"></div></div>';
        this.disabled = true;
        app.querySelectorAll(".jbtn").forEach(function (b) {
          b.onclick = function () {
            advisorState.judgment = b.getAttribute("data-j");
            app.querySelectorAll(".jbtn").forEach(function (x) { x.disabled = true; });
            b.classList.add("picked");
            document.getElementById("jnote").textContent =
              "\u0412\u0435\u0440\u0434\u0438\u043a\u0442 \u0437\u0430\u043f\u0438\u0441\u0430\u043d. \u0412\u0435\u0440\u0435\u043d \u043b\u0438 \u043e\u043d \u2014 \u0443\u0437\u043d\u0430\u0435\u0442\u0435 \u043f\u043e\u0441\u043b\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u044f.";
          };
        });
      };
    };
  }

  function wireOptions(node) {
    app.querySelectorAll(".opt").forEach(function (b) {
      b.onclick = function () { commitChoice(node, optById(b.getAttribute("data-oid"))); };
    });
  }

  function commitChoice(node, o) {
    var before = JSON.parse(JSON.stringify(session.state));
    scenario.meta.kpis.forEach(function (m) { session.state[m.key] += (o.kpi[m.key] || 0); });
    var rec = {
      type: "choice", node: node.id, time: node.time, title: node.title, advisor: !!node.advisor,
      prompt: advisorState ? advisorState.prompt : null, promptScore: advisorState ? advisorState.promptScore : null,
      promptRelevant: advisorState ? advisorState.promptRelevant : null, prediction: advisorState ? advisorState.prediction : null,
      adviceOption: advisorState && advisorState.advice ? advisorState.advice.recommend : null,
      adviceCorrect: advisorState && advisorState.advice ? advisorState.advice.correct : null,
      verified: advisorState ? advisorState.verified : false,
      verifyJudgment: advisorState ? advisorState.judgment : null,
      judgmentCorrect: advisorState && advisorState.advice && advisorState.judgment
        ? ((advisorState.judgment === "flawed") === !advisorState.advice.correct) : null,
      choice: o.id, choiceLabel: o.label, choiceQuality: o.quality,
      followedAdvice: advisorState && advisorState.advice ? o.id === advisorState.advice.recommend : null,
      intentMs: advisorState && advisorState.intentAt ? advisorState.intentAt - nodeEnterTime : null,
      dwellMs: Date.now() - nodeEnterTime, theoryOpened: theoryOpenedPre,
      kpiBefore: before, kpiAfter: JSON.parse(JSON.stringify(session.state)),
    };
    session.log.push(rec); session.history.push(o.next); save();
    showFeedback(node, o, rec);
  }

  function showFeedback(node, o, rec) {
    var rows = scenario.meta.kpis.map(function (m) {
      var dv = o.kpi[m.key] || 0; if (dv === 0) return "";
      return '<div class="frow ' + deltaClass(m.key, dv) + '"><span>' + m.label + "</span><span>" +
        fmt(m.key, rec.kpiBefore[m.key]) + " \u2192 " + fmt(m.key, rec.kpiAfter[m.key]) +
        '</span><span class="dv">' + (dv > 0 ? "+" : "") + dv + "</span></div>";
    }).join("");
    var qmark = { good: "\u2713", warn: "\u26a0", bad: "\u2715" }[o.quality];
    var aiDebrief = "";
    if (rec.adviceOption && node.advisor) {
      var advData = AIAdvisor.ADVICE[node.id];
      var verdictLine = "";
      if (rec.verifyJudgment) {
        verdictLine = '<div class="jres ' + (rec.judgmentCorrect ? "ok" : "no") + '">\u0412\u0430\u0448 \u0432\u0435\u0440\u0434\u0438\u043a\u0442 \u0431\u044b\u043b ' +
          (rec.judgmentCorrect ? "\u0432\u0435\u0440\u043d\u044b\u043c" : "\u043d\u0435\u0432\u0435\u0440\u043d\u044b\u043c") + ": \u0441\u043e\u0432\u0435\u0442 " +
          (rec.adviceCorrect ? "\u0432\u044b\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u043b \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443." : "\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043b \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0435.") + "</div>";
      } else if (rec.verified) {
        verdictLine = '<div class="jres">\u0412\u044b \u043e\u0442\u043a\u0440\u044b\u043b\u0438 \u0440\u0430\u0441\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u0435, \u043d\u043e \u043d\u0435 \u0432\u044b\u043d\u0435\u0441\u043b\u0438 \u0432\u0435\u0440\u0434\u0438\u043a\u0442.</div>';
      } else {
        verdictLine = '<div class="jres">\u0412\u044b \u043d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u043b\u0438 \u043e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0441\u043e\u0432\u0435\u0442\u0430.</div>';
      }
      aiDebrief = '<div class="aidebrief"><div class="rl">\u0420\u0430\u0437\u0431\u043e\u0440 \u0441\u043e\u0432\u0435\u0442\u0430 \u0418\u0418 \u00b7 \u0441\u043e\u0432\u0435\u0442 \u0431\u044b\u043b ' +
        (rec.adviceCorrect ? "\u0432\u0435\u0440\u043d\u044b\u043c" : "\u043e\u0448\u0438\u0431\u043e\u0447\u043d\u044b\u043c") + "</div>" + verdictLine +
        '<p class="fbtext">' + esc(advData ? advData.debrief : "") + "</p></div>";
    }
    var overlay = document.createElement("div");
    overlay.className = "overlay";
    overlay.innerHTML = '<div class="fbcard q-' + o.quality + '">' +
      '<div class="fbtop"><span class="qbadge">' + qmark + '</span><span class="fbtitle">' + esc(o.label) + "</span></div>" +
      '<div class="fbbody"><p class="fbtext">' + esc(o.feedback) + "</p>" + aiDebrief +
      '<div class="deltas">' + rows + "</div>" +
      '<div class="fbactions"><button class="ghost" id="reTheory">\u041f\u0435\u0440\u0435\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u0442\u0435\u043e\u0440\u0438\u044e</button>' +
      '<button class="primary" id="fnext">\u0414\u0430\u043b\u0435\u0435 \u25b6</button></div></div></div>';
    app.appendChild(overlay);
    document.getElementById("reTheory").onclick = function () {
      rec.theoryOpened = true; save();
      openTheory(node);
    };
    document.getElementById("fnext").onclick = function () {
      session.currentNode = o.next;
      if (scenario.nodes[o.next].type === "final") { session.done = true; session.finishedAt = Date.now(); }
      save(); overlay.remove(); render();
    };
  }

  function renderFinal() {
    var m = Metrics.compute(session, scenario);
    try {
      var payload = {
        sessionId: session.sessionId,
        startedAt: session.startedAt,
        finishedAt: session.finishedAt,
        score: m.score,
        coverage: m.coverage,
        metrics: m.raw,
        details: m.groups,
      };
      console.log("[research] Процессные метрики прохождения. Участнику не показываются и в интерфейс не выводятся.");
      console.log("[research] Сессия " + session.sessionId + " · интегральный балл: " +
        (m.score == null ? "—" : m.score) + " · покрытие: " + m.coverage);
      console.log(JSON.stringify(payload, null, 2));
      var store = [];
      try { store = JSON.parse(localStorage.getItem("delivergo:research") || "[]"); } catch (e) {}
      store = store.filter(function (p) { return p.sessionId !== payload.sessionId; });
      store.push(payload);
      localStorage.setItem("delivergo:research", JSON.stringify(store));
      console.log("[research] Копия сохранена в localStorage под ключом delivergo:research (все сессии этого устройства).");
    } catch (e) {
      console.error("[research] Не удалось записать метрики:", e);
    }
    var kpiCards = scenario.meta.kpis.map(function (k) {
      var v = session.state[k.key], met, fill;
      if (k.goal === "min") { met = v <= (k.target + 0.001); fill = v <= 0 ? 100 : Math.max(8, 100 - v * 12); }
      else if (k.goal === "band") { met = Math.abs(v - k.target) <= 15; fill = Math.min(100, (v / k.target) * 100); }
      else { met = v >= k.target; fill = Math.min(100, (v / k.target) * 100); }
      return '<div class="rk ' + (met ? "met" : "miss") + '"><div class="rkl">' + k.label + '</div>' +
        '<div class="rkv">' + fmt(k.key, v) + ' <span class="rkt">/ ' + fmt(k.key, k.target) + "</span></div>" +
        '<div class="bar"><i style="width:' + Math.max(4, Math.round(fill)) + '%"></i></div></div>';
    }).join("");

    var chron = session.log.filter(function (r) { return r.type === "choice"; }).map(function (r) {
      var qm = { good: "\u2713", warn: "\u26a0", bad: "\u2715" }[r.choiceQuality];
      return '<li class="q-' + r.choiceQuality + '"><span class="ct">' + r.time + '</span><span class="cn">' + esc(r.title) + "</span>" +
        '<span class="cc"><span class="qm">' + qm + "</span> " + esc(r.choiceLabel) + "</span>" +
        (r.advisor ? '<span class="cai">' + (r.followedAdvice ? "\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043b \u0418\u0418" : "\u043e\u0442\u043a\u043b\u043e\u043d\u0438\u043b \u0418\u0418") + (r.verified ? " \u00b7 \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b" : "") + "</span>" : "") + "</li>";
    }).join("");

    var misses = [];
    session.log.filter(function (r) { return r.type === "choice" && r.choiceQuality !== "good"; })
      .forEach(function (r) {
        var nd = scenario.nodes[r.node]; if (!nd || !nd.options) return;
        var best = null;
        nd.options.forEach(function (op) {
          if (op.quality === "good" && (!best || (op.kpi.profit || 0) > (best.kpi.profit || 0))) best = op;
        });
        if (!best) return;
        var chosen = nd.options.filter(function (op) { return op.id === r.choice; })[0] || { kpi: {} };
        var dP = (best.kpi.profit || 0) - (chosen.kpi.profit || 0);
        var dS = (best.kpi.sla || 0) - (chosen.kpi.sla || 0);
        var dT = (best.kpi.team || 0) - (chosen.kpi.team || 0);
        if (dP || dS || dT) misses.push({ r: r, best: best, dP: dP, dS: dS, dT: dT });
      });
    misses.sort(function (a, b) { return b.dP - a.dP; });
    var whatif = misses.slice(0, 2).map(function (m2) {
      var d3 = [];
      if (m2.dP) d3.push((m2.dP > 0 ? "+" : "") + m2.dP.toLocaleString("ru-RU") + " ₽ прибыли");
      if (m2.dS) d3.push((m2.dS > 0 ? "+" : "") + m2.dS + " SLA");
      if (m2.dT) d3.push((m2.dT > 0 ? "+" : "") + m2.dT + " команда");
      return '<div class="wirow"><span class="wit">' + esc(m2.r.time) + " · " + esc(m2.r.title) + "</span>" +
        '<span class="wic">вы: «' + esc(m2.r.choiceLabel) + "»</span>" +
        '<span class="wib">сильнее: «' + esc(m2.best.label) + "» (" + d3.join(", ") + ")</span></div>";
    }).join("");
    var reflPrev = "";
    session.log.forEach(function (r) { if (r.type === "reflection") reflPrev = r.text; });
    var debriefBlock = '<h2>Разбор дня</h2><div class="debrief">' +
      (whatif ? '<div class="rl">Что можно было сделать иначе:</div>' + whatif
              : '<div class="rl">Все ключевые развилки пройдены сильными решениями.</div>') +
      '<div class="rl" style="margin-top:14px">Ваш главный вывод — какой принцип примените завтра и почему?</div>' +
      '<textarea id="refl" rows="3" placeholder="Сформулируйте своими словами: это и есть момент обучения">' + esc(reflPrev) + "</textarea>" +
      '<div class="reflrow"><button class="ghost" id="reflSave">Сохранить вывод</button><span id="reflNote" class="jnote">' +
      (reflPrev ? "сохранено" : "") + "</span></div>" +
      '<p class="replaygoal">Хотите закрепить? Пройдите день заново: попробуйте поймать все ошибочные советы ИИ, закончить день без слабых решений и удержать команду выше 60%.</p></div>';

    var tp = session.state.profit, hit = tp >= 300000;
    var mapBlock = '<div class="mapcard"><div class="maphead">' +
      '<span class="maptitle">\u041a\u0430\u0440\u0442\u0430 \u043f\u0440\u043e\u0439\u0434\u0435\u043d\u043d\u043e\u0433\u043e \u0434\u043d\u044f</span>' +
      '<span class="maplegend"><span><span class="lg g"></span>\u0445\u043e\u0440\u043e\u0448\u043e</span>' +
      '<span><span class="lg w"></span>\u0441\u043f\u043e\u0440\u043d\u043e</span>' +
      '<span><span class="lg b"></span>\u043f\u043b\u043e\u0445\u043e</span></span></div>' + journeyMap() + "</div>";

    var html = '<section class="results">' +
      '<div class="pnl ' + (hit ? "" : "miss") + '"><div class="pnllabel">\u0418\u0442\u043e\u0433 \u0434\u043d\u044f \u00b7 \u041f\u0440\u0438\u0431\u044b\u043b\u044c</div>' +
      '<div class="pnlbig">' + (tp >= 0 ? "+" : "") + tp.toLocaleString("ru-RU") + ' \u20bd</div>' +
      '<div class="pnlsub">\u0446\u0435\u043b\u044c 300\u202f000 \u20bd \u00b7 ' + (hit ? "\u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430" : "\u043d\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u0430") + " \u00b7 \u0437\u0432\u0451\u0437\u0434 \u0437\u0430 \u0440\u0435\u0448\u0435\u043d\u0438\u044f: " + starCount() + "/" + choiceStages().length + "</div></div>" +
      "<h2>\u0418\u0442\u043e\u0433\u043e\u0432\u044b\u0435 \u043f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u0438</h2>" + '<div class="rkgrid">' + kpiCards + "</div>" +
      "<h2>\u041c\u0430\u0440\u0448\u0440\u0443\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u0439</h2>" + mapBlock +
      debriefBlock +
      "<h2>\u0425\u0440\u043e\u043d\u0438\u043a\u0430 \u0434\u043d\u044f</h2>" + '<ol class="chron">' + chron + "</ol>" +
      '<div class="rawbox"><button class="ghost" id="rawtoggle">\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u044b\u0440\u043e\u0439 \u043b\u043e\u0433 (localStorage)</button><pre id="raw" hidden></pre></div>' +
      '<button class="primary full" id="again">\u041f\u0440\u043e\u0439\u0442\u0438 \u0437\u0430\u043d\u043e\u0432\u043e</button></section>';
    shell(html, {});

    var reflBtn = document.getElementById("reflSave");
    if (reflBtn) reflBtn.onclick = function () {
      var txt = (document.getElementById("refl").value || "").trim();
      if (!txt) return;
      session.log = session.log.filter(function (r) { return r.type !== "reflection"; });
      session.log.push({ type: "reflection", text: txt, ts: Date.now() });
      save();
      document.getElementById("reflNote").textContent = "сохранено · попадёт в лог сессии";
    };
    document.getElementById("rawtoggle").onclick = function () {
      var pre = document.getElementById("raw"); pre.hidden = !pre.hidden;
      pre.textContent = JSON.stringify(session, null, 2);
      this.textContent = pre.hidden ? "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u044b\u0440\u043e\u0439 \u043b\u043e\u0433 (localStorage)" : "\u0421\u043a\u0440\u044b\u0442\u044c \u043b\u043e\u0433";
    };
    document.getElementById("again").onclick = function () { newSession(); render(); };
  }

  function boot() {
    fetch("scenario.json")
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) { scenario = data; if (!loadSession() || !session.currentNode) newSession(); render(); })
      .catch(function (e) {
        app.innerHTML = '<div class="loaderr"><h1>\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c scenario.json</h1>' +
          "<p>\u0411\u0440\u0430\u0443\u0437\u0435\u0440\u044b \u0431\u043b\u043e\u043a\u0438\u0440\u0443\u044e\u0442 fetch \u043f\u043e file://. \u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0441\u0442\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u0435\u0440\u0432\u0435\u0440: <code>python3 -m http.server 8000</code>, \u0437\u0430\u0442\u0435\u043c \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 <code>http://localhost:8000</code>.</p><p class=\"err\">" + esc(String(e)) + "</p></div>";
      });
  }
  boot();
})();
