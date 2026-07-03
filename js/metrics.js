(function (global) {
  "use strict";

  var Q = { good: 2, warn: 1, bad: 0 };

  function pct(x) { return Math.round(x * 100); }

  function slope(ys) {
    var n = ys.length;
    if (n < 2) return 0;
    var sx = 0, sy = 0, sxy = 0, sxx = 0;
    for (var i = 0; i < n; i++) { sx += i; sy += ys[i]; sxy += i * ys[i]; sxx += i * i; }
    var denom = n * sxx - sx * sx;
    return denom === 0 ? 0 : (n * sxy - sx * sy) / denom;
  }

  function compute(session, scenario) {
    var log = session.log || [];
    var choices = log.filter(function (r) { return r.type === "choice"; });
    var advisorNodes = choices.filter(function (r) { return r.advisor; });
    var asked = advisorNodes.filter(function (r) { return r.adviceOption; });
    var consultRate = advisorNodes.length ? asked.length / advisorNodes.length : null;

    
    var correctAdvice = asked.filter(function (r) { return r.adviceCorrect; });
    var wrongAdvice = asked.filter(function (r) { return !r.adviceCorrect; });

    
    var overFollow = wrongAdvice.filter(function (r) { return r.followedAdvice; }).length;
    var underIgnore = correctAdvice.filter(function (r) { return !r.followedAdvice; }).length;
    var overRely = wrongAdvice.length ? overFollow / wrongAdvice.length : null;
    var underRely = correctAdvice.length ? underIgnore / correctAdvice.length : null;

    
    var rairDen = correctAdvice.filter(function (r) {
      return r.prediction != null && r.prediction !== r.adviceOption;
    });
    var rairNum = rairDen.filter(function (r) { return r.choice === r.adviceOption; }).length;
    var rair = rairDen.length ? rairNum / rairDen.length : null;

    
    var rsrDen = wrongAdvice.filter(function (r) {
      return r.prediction != null && r.prediction !== r.adviceOption;
    });
    var rsrNum = rsrDen.filter(function (r) { return r.choice !== r.adviceOption; }).length;
    var rsr = rsrDen.length ? rsrNum / rsrDen.length : null;

   
    var detrimentalSwitch = rsrDen.length - rsrNum;

    var arParts = [rair, rsr].filter(function (v) { return v != null; });
    var arIndex = arParts.length
      ? arParts.reduce(function (a, b) { return a + b; }, 0) / arParts.length
      : (overRely != null || underRely != null
          ? 1 - 0.5 * (overRely || 0) - 0.5 * (underRely || 0)
          : null);

    var switched = asked.filter(function (r) {
      return r.prediction != null && r.choice !== r.prediction;
    }).length;
    var switchRate = asked.length ? switched / asked.length : null;

    
    var verified = asked.filter(function (r) { return r.verified; });
    var verifyRate = asked.length ? verified.length / asked.length : null;
    var judged = asked.filter(function (r) { return r.verifyJudgment != null; });
    var judgedRight = judged.filter(function (r) {
      return (r.verifyJudgment === "flawed") === !r.adviceCorrect;
    }).length;
    var judgeAcc = judged.length ? judgedRight / judged.length : null;
    
    var caught = wrongAdvice.filter(function (r) { return r.choice !== r.adviceOption; }).length;
    var errorCatchRate = wrongAdvice.length ? caught / wrongAdvice.length : null;

   
    var prompted = asked.filter(function (r) { return r.promptScore != null; });
    var avgPrompt = prompted.length
      ? prompted.reduce(function (s, r) { return s + r.promptScore; }, 0) / prompted.length
      : null;
    var relevantRate = prompted.length
      ? prompted.filter(function (r) { return r.promptRelevant; }).length / prompted.length
      : null;

    
    var qualitySeq = choices.map(function (r) { return Q[r.choiceQuality]; });
    var improvement = slope(qualitySeq);
    var recovered = 0, recoverable = 0;
    for (var i = 0; i < choices.length - 1; i++) {
      if (choices[i].choiceQuality !== "good") {
        recoverable++;
        if (Q[choices[i + 1].choiceQuality] > Q[choices[i].choiceQuality]) recovered++;
      }
    }
    var recoveryRate = recoverable ? recovered / recoverable : null;

    
    var meta = scenario.meta;
    var fam = meta.variability_family || [];
    var famNodes = {};
    Object.keys(scenario.nodes).forEach(function (nid) {
      (scenario.nodes[nid].options || []).forEach(function (o) {
        if (fam.indexOf(o.id) >= 0) famNodes[nid] = o.id;
      });
    });
    var introNode = meta.variability_family_intro;
    var famAfter = choices.filter(function (r) {
      return famNodes[r.node] && r.node !== introNode;
    });
    var consistentPicks = famAfter.filter(function (r) { return r.choice === famNodes[r.node]; }).length;
    var consistency = famAfter.length ? consistentPicks / famAfter.length : null;

    
    var transferRec = choices.filter(function (r) { return r.node === meta.transfer_node; })[0];
    var autonomous = transferRec
      ? (transferRec.choiceQuality === "good" ? 1 : (transferRec.choiceQuality === "warn" ? 0.5 : 0))
      : null;
    var transferParts = [consistency, autonomous].filter(function (v) { return v != null; });
    var transfer = transferParts.length
      ? transferParts.reduce(function (a, b) { return a + b; }, 0) / transferParts.length
      : null;

    
    var bp = meta.boundary_probe || {};
    var bpRec = choices.filter(function (r) { return r.node === bp.node; })[0];
    var boundaryNote = "";
    if (bpRec && bp.option) {
      if (bpRec.choice === bp.option) {
        boundaryNote = "На граничной развилке (усталость команды) принцип «снизь вариативность» "
          + "применён за пределами своей зоны: процессу помогло, но узкое место — люди.";
      } else if (bpRec.choice === bp.better) {
        boundaryNote = "На граничной развилке распознана граница применимости принципа: "
          + "узкое место — усталость, выбрана свежая подмена.";
      }
    }

    
    var dwellVals = choices.map(function (r) { return r.dwellMs || 0; });
    var avgDwell = dwellVals.length
      ? dwellVals.reduce(function (a, b) { return a + b; }, 0) / dwellVals.length : 0;
    var theoryOpens = choices.filter(function (r) { return r.theoryOpened; }).length;
    
    var offloadingSignals = wrongAdvice.filter(function (r) {
      return r.followedAdvice && !r.verified && (r.dwellMs || 0) < 6000;
    }).length;

    var normSlope = Math.max(0, Math.min(1, (improvement + 0.3) / 0.6)); 
    var components = [
      { w: 0.25, v: arIndex },
      { w: 0.20, v: judgeAcc },
      { w: 0.15, v: avgPrompt == null ? null : avgPrompt / 4 },
      { w: 0.20, v: transfer },
      { w: 0.10, v: choices.length >= 2 ? normSlope : null },
      { w: 0.10, v: errorCatchRate },
    ];
    var wSum = 0, acc = 0, covered = 0;
    components.forEach(function (c) {
      if (c.v != null) { wSum += c.w; acc += c.w * c.v; covered++; }
    });
    var processScore = wSum > 0 ? Math.round((acc / wSum) * 100) : null;
    var coverage = covered + " из " + components.length;

    
    function fmtOrDash(v, suffix) { return v == null ? "—" : pct(v) + (suffix || "%"); }

    return {
      score: processScore,
      coverage: coverage,
      groups: [
        {
          dim: "К3 · Калибровка опоры на ИИ",
          key: "RAIR / RSR (полезные и вредные переключения)",
          value: (arIndex == null ? "—" : pct(arIndex) + " / 100"),
          detail: "Обращений к ИИ: " + asked.length + " из " + advisorNodes.length
            + ". RAIR (переключился к верному совету при ином намерении): " + fmtOrDash(rair)
            + " (" + rairNum + "/" + rairDen.length + "). RSR (устоял перед ошибочным): "
            + fmtOrDash(rsr) + " (" + rsrNum + "/" + rsrDen.length + "). Вредных переключений: "
            + detrimentalSwitch + ". Переключений после совета всего: " + fmtOrDash(switchRate) + ".",
          why: "Совпадение выбора с советом ≠ опора на совет: без учёта намерения «до» пере-опору не отличить от собственного мнения (Schemmer et al., 2023).",
        },
        {
          dim: "К2 · Критическая оценка вывода",
          key: "Точность проверки обоснований",
          value: (judgeAcc == null ? "—" : pct(judgeAcc) + "%"),
          detail: "Открывал рассуждение модели: " + fmtOrDash(verifyRate) + " обращений; вынес вердикт: "
            + judged.length + " (верных вердиктов: " + judgedRight + "). Поведенчески отклонено "
            + caught + " из " + wrongAdvice.length + " посеянных ошибочных советов.",
          why: "Клик «проверить» легко накрутить; оценивается суждение — нашёл ли участник посеянное противоречие между рассуждением и прогнозом (Buçinca et al., 2021).",
        },
        {
          dim: "К1 · Постановка инструкции",
          key: "Качество запросов к ИИ",
          value: (avgPrompt == null ? "—" : avgPrompt.toFixed(1) + " / 4"),
          detail: "Релевантных запросов: " + fmtOrDash(relevantRate)
            + ". Балл растёт за цель/ограничение, ссылку на состояние, запрос вариантов и обоснования.",
          why: "Отличает делегирование («что делать?») от постановки задачи с контекстом и ограничениями — измеримая грань ИИ-грамотности (UNESCO, 2024; EC–OECD, 2026).",
        },
        {
          dim: "К4 · Итеративность и реакция",
          key: "Наклон улучшения стратегии",
          value: (improvement >= 0 ? "+" : "") + improvement.toFixed(2) + " / шаг",
          detail: "Коррекция после неудачи: " + fmtOrDash(recoveryRate)
            + " случаев улучшения на следующем шаге.",
          why: "Ловит траекторию научения, а не только конечную точку — участник адаптируется по ходу.",
        },
        {
          dim: "К5 · Перенос принципа",
          key: "Ближний перенос + автономное применение",
          value: (transfer == null ? "—" : pct(transfer) + "%"),
          detail: "Внутри дня (сет-меню для корпоратива после экспресс-меню): " + fmtOrDash(consistency)
            + ". «Холодный» тест без ИИ (утро следующего дня): "
            + (autonomous == null ? "—" : (autonomous === 1 ? "принцип применён" : (autonomous === 0.5 ? "частично" : "не применён")))
            + ". " + boundaryNote,
          why: "С ИИ результат растёт, но знание может не оставаться (Bastani et al., 2025); поэтому цикл замыкается проверкой БЕЗ ассистента.",
        },
        {
          dim: "К5 · Саморегуляция",
          key: "Метакогнитивный профиль",
          value: (avgDwell / 1000).toFixed(1) + " c/решение",
          detail: "Обращений к теории: " + theoryOpens + ". Сигналов офлоадинга (быстро + слепо за "
            + "ошибочным советом): " + offloadingSignals + ".",
          why: "Скорость сама по себе неоднозначна; в связке с опорой и проверкой становится диагностичной (Gerlich, 2025).",
        },
      ],
      raw: {
        consultRate: consultRate, overRely: overRely, underRely: underRely,
        rair: rair, rsr: rsr, detrimentalSwitch: detrimentalSwitch,
        arIndex: arIndex, switchRate: switchRate,
        verifyRate: verifyRate, judgeAcc: judgeAcc, judgedCount: judged.length,
        errorCatchRate: errorCatchRate,
        avgPrompt: avgPrompt, relevantRate: relevantRate,
        improvement: improvement, recoveryRate: recoveryRate,
        consistency: consistency, autonomousTransfer: autonomous, transfer: transfer,
        avgDwellMs: avgDwell, theoryOpens: theoryOpens,
        offloadingSignals: offloadingSignals,
      },
    };
  }

  global.Metrics = { compute: compute };
})(typeof window !== "undefined" ? window : globalThis);
