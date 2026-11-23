(() => {
  "use strict";

  const STORAGE_SAVED = "goyang_able_saved_v2";
  const STORAGE_FONT = "goyang_able_font_v2";
  const STORAGE_CONTRAST = "goyang_able_contrast_v2";

  let allJobs = [];
  let metaData = null;
  let savedIds = new Set(loadJson(STORAGE_SAVED, []));

  const state = {
    view: "list",         // list | map
    query: "",
    zone: "all",
    org: "public",        // public(공공·지자체, 기본값) | all | major | general
    status: "active",     // active(접수중) | closed | all
    worktype: "fulltime", // fulltime(전일제 주5일↑, 기본값) | parttime(단시간·시간제) | all
    severity: "mild_ok",  // mild_ok(경증도 지원 가능, 기본값) | all | severe_only
    contract: "all",
    sourceId: "all",
    sort: "new_first",    // new_first(신규 공고 우선, 기본값)
    onlyNew: false,
    toggles: {
      welfare_job: false,   // 기본값 false: 국가/지자체 장애인일자리사업 제외, 켜면 그것만 따로 모아보기
      remote: false,
      disabled_only: false,
      hide_restricted: false,
      saved_only: false,
    },
  };

  function loadJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function saveIdsToStorage() {
    localStorage.setItem(STORAGE_SAVED, JSON.stringify([...savedIds]));
    document.getElementById("saved-count").textContent = String(savedIds.size);
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const WEEKDAYS_KO = ["일", "월", "화", "수", "목", "금", "토"];

  function parseIsoDate(str) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((str || "").trim());
    if (!m) return null;
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  }

  function formatKoDate(dt) {
    if (!dt) return "";
    const y = dt.getFullYear();
    const mo = String(dt.getMonth() + 1).padStart(2, "0");
    const dy = String(dt.getDate()).padStart(2, "0");
    const wd = WEEKDAYS_KO[dt.getDay()];
    return `${y}-${mo}-${dy} (${wd})`;
  }

  function shortMd(dt) {
    if (!dt) return "";
    return `${dt.getMonth() + 1}/${dt.getDate()}`;
  }

  function computeApplicationStatus(job) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startDt = parseIsoDate(job.application_start);
    const endDt = parseIsoDate(job.deadline);

    if (job.is_closed_in_text) {
      const endLabel = endDt ? formatKoDate(endDt) : (job.deadline || "종료");
      return {
        code: "closed",
        badge: endDt ? `⛔ 마감 (${shortMd(endDt)})` : "⛔ 접수마감",
        badgeClass: "badge-status-closed",
        deadlineText: `${endLabel} · 접수마감`,
        periodText: startDt ? `${formatKoDate(startDt)} ~ ${endLabel} (마감)` : `${endLabel} (마감)`,
        days: 99999,
      };
    }

    if (endDt) {
      const diff = Math.round((endDt - today) / 86400000);
      const endKo = formatKoDate(endDt);
      const rangeNote = startDt ? ` (접수 ${shortMd(startDt)}~${shortMd(endDt)})` : "";
      if (diff < 0) {
        return {
          code: "closed",
          badge: `⛔ 마감 (${shortMd(endDt)})`,
          badgeClass: "badge-status-closed",
          deadlineText: `${endKo} · ${Math.abs(diff)}일 전 마감`,
          periodText: `${endKo} 마감${rangeNote}`,
          days: 99999 + Math.abs(diff),
        };
      }
      if (startDt && startDt > today) {
        const sDiff = Math.round((startDt - today) / 86400000);
        return {
          code: "upcoming",
          badge: `🗓️ 접수예정 (~${shortMd(endDt)})`,
          badgeClass: "badge-status-upcoming",
          deadlineText: `${endKo} 마감 (D-${diff} · ${shortMd(startDt)} 접수시작, ${sDiff}일 후)`,
          periodText: `${formatKoDate(startDt)} ~ ${endKo}`,
          days: diff,
        };
      }
      if (diff === 0) {
        return {
          code: "soon",
          badge: `🔥 오늘 마감 (${shortMd(endDt)})`,
          badgeClass: "badge-status-soon",
          deadlineText: `${endKo} · 오늘 마감 (D-Day)${rangeNote}`,
          periodText: `${endKo} (오늘 마감)${rangeNote}`,
          days: 0,
        };
      }
      if (diff <= 7) {
        return {
          code: "soon",
          badge: `🔥 D-${diff} 마감 (~${shortMd(endDt)})`,
          badgeClass: "badge-status-soon",
          deadlineText: `${endKo} · D-${diff} 마감임박${rangeNote}`,
          periodText: `${endKo} (D-${diff})${rangeNote}`,
          days: diff,
        };
      }
      return {
        code: "open",
        badge: `🟢 접수중 (~${shortMd(endDt)} · D-${diff})`,
        badgeClass: "badge-status-open",
        deadlineText: `${endKo} · D-${diff}${rangeNote}`,
        periodText: `${endKo} (D-${diff})${rangeNote}`,
        days: diff,
      };
    }

    if (startDt && startDt > today) {
      return {
        code: "upcoming",
        badge: `🗓️ 접수예정 (${shortMd(startDt)}~)`,
        badgeClass: "badge-status-upcoming",
        deadlineText: `채용시까지 (${formatKoDate(startDt)} 접수시작)`,
        periodText: `${formatKoDate(startDt)} ~ 채용시까지`,
        days: 8000,
      };
    }

    const fallbackDl = job.deadline || "채용시까지";
    return {
      code: "open",
      badge: fallbackDl === "채용시까지" ? "🟢 상시 (채용시까지)" : `🟢 접수중 (${fallbackDl})`,
      badgeClass: "badge-status-open",
      deadlineText: fallbackDl === "채용시까지" ? "채용시까지 (상시접수)" : fallbackDl,
      periodText: fallbackDl,
      days: 9999,
    };
  }

  function severityBadgeClass(sev) {
    if (sev === "중증만 가능" || sev === "중증 우대") return "badge-sev-severe";
    if (sev === "경증만 가능") return "badge-sev-mild";
    if (sev === "중증·경증 무관") return "badge-sev-any";
    return "badge-other";
  }

  function isWelfarePublicJob(job) {
    const t = job.title || "";
    const emp = job.employment_type || "";
    // 교육공무직원 등 정규 무기계약 채용은 제외
    if (emp === "무기계약직" && /교육공무직/.test(t)) return false;
    if (emp === "공공일자리") return true;
    return /장애인\s*(?:일반형|복지|특화형|맞춤형)?\s*일자리\s*(?:지원)?(?:사업)?|행정도우미|권리중심/.test(t);
  }

  function isPartTimeJob(job) {
    if (job.is_part_time) return true;
    const emp = job.employment_type || "";
    const wh = job.work_hours || "";
    const title = job.title || "";
    if (emp === "시간제") return true;
    if (/단시간|시간제|파트타임|격일|주\s*[1-4]일/.test(wh)) return true;
    if (/일\s*[1-6](?:\.\d)?\s*시간|하루\s*[1-6](?:\.\d)?\s*시간/.test(`${wh} ${title}`)) return true;
    const mWk = /주\s*(\d{1,2})\s*시간/.exec(wh);
    if (mWk && Number(mWk[1]) <= 34) return true;
    return false;
  }

  function formatSalaryDisplay(job) {
    const raw = (job.salary_text || "회사내규 / 상세 참고").trim();
    // 이미 연봉 표기면 원문 그대로 반환
    if (/연봉/.test(raw)) {
      return { text: raw, html: escapeHtml(raw) };
    }

    let estAnnualManwon = null;

    // 1) 시급 표기인 경우 근무시간 반영해 예측 연봉 계산
    const mHourly = /시급[^\d]*([\d,]+)\s*원/.exec(raw);
    if (mHourly) {
      const hourly = Number(mHourly[1].replace(/,/g, ""));
      if (hourly >= 8000 && hourly <= 200000) {
        const wh = job.work_hours || "";
        let weeklyHours = 40;
        const mWkH = /주\s*(\d{1,2}(?:\.\d)?)\s*시간/.exec(wh);
        const mDayH = /(?:일|하루)\s*(\d(?:\.\d)?)\s*시간/.exec(wh);
        const mDays = /주\s*([1-6])\s*일/.exec(wh);
        const days = mDays ? Number(mDays[1]) : 5;
        if (mWkH) {
          weeklyHours = Number(mWkH[1]);
        } else if (mDayH) {
          weeklyHours = Number(mDayH[1]) * days;
        } else if (isPartTimeJob(job)) {
          weeklyHours = 20;
        }
        // 주 15시간 이상이면 주휴수당 포함(1.2배), 주 40시간 기준 월 209시간
        const monthlyPaidHours =
          weeklyHours >= 40
            ? 209
            : weeklyHours >= 15
              ? weeklyHours * 1.2 * 4.345
              : weeklyHours * 4.345;
        estAnnualManwon = Math.round((hourly * monthlyPaidHours * 12) / 10000);
      }
    }

    // 2) 월급 표기이거나 salary_monthly_krw가 있는 경우 (월급 × 12)
    if (!estAnnualManwon && job.salary_monthly_krw && job.salary_monthly_krw >= 30) {
      estAnnualManwon = Math.round(job.salary_monthly_krw * 12);
    }

    if (estAnnualManwon && estAnnualManwon >= 300) {
      const formattedAnnual = estAnnualManwon.toLocaleString("ko-KR");
      const text = `연봉 약 ${formattedAnnual}만원 (${raw} · 예측치)`;
      const html = `연봉 약 ${formattedAnnual}만원 <span class="salary-est-note">(${escapeHtml(raw)} · 예측치)</span>`;
      return { text, html };
    }

    return { text: raw, html: escapeHtml(raw) };
  }

  function zoneBadgeClass(zone) {
    if (zone === "고양시 관내") return "badge-goyang";
    if (zone === "인접 출퇴근") return "badge-nearby";
    if (zone === "재택근무") return "badge-remote";
    return "badge-other";
  }

  function zoneEmoji(zone) {
    if (zone === "고양시 관내") return "🟢 ";
    if (zone === "인접 출퇴근") return "🔵 ";
    if (zone === "재택근무") return "🟣 ";
    return "";
  }

  /* 접근성 설정 초기화 */
  function initA11y() {
    const savedFont = localStorage.getItem(STORAGE_FONT) || "normal";
    applyFont(savedFont);

    const savedContrast = localStorage.getItem(STORAGE_CONTRAST) || "normal";
    applyContrast(savedContrast === "high");

    document.querySelectorAll("[data-font]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const size = btn.dataset.font;
        applyFont(size);
        localStorage.setItem(STORAGE_FONT, size);
      });
    });

    const contrastBtn = document.getElementById("contrast-btn");
    contrastBtn.addEventListener("click", () => {
      const next = document.documentElement.dataset.contrast !== "high";
      applyContrast(next);
      localStorage.setItem(STORAGE_CONTRAST, next ? "high" : "normal");
    });
  }

  function applyFont(size) {
    document.documentElement.dataset.font = size;
    document.querySelectorAll("[data-font]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.font === size));
    });
  }

  function applyContrast(isHigh) {
    document.documentElement.dataset.contrast = isHigh ? "high" : "normal";
    const btn = document.getElementById("contrast-btn");
    btn.setAttribute("aria-pressed", String(isHigh));
    btn.textContent = isHigh ? "일반 모드" : "고대비 모드";
  }

  /* 메타 & 출처 패널 렌더링 */
  function renderMeta() {
    if (!metaData) return;
    document.getElementById("updated-badge").textContent = `최근 업데이트: ${metaData.updated_at || "-"}`;
    document.getElementById("model-badge").textContent = `정제 엔진: ${metaData.model || "DeepSeek 4.1"}`;
    document.getElementById("kpi-total").textContent = `${metaData.total_jobs ?? allJobs.length}건`;
    document.getElementById("kpi-goyang").textContent = `${metaData.goyang_count ?? 0}건`;
    document.getElementById("kpi-nearby").textContent = `${metaData.nearby_count ?? 0}건`;
    document.getElementById("kpi-remote").textContent = `${metaData.remote_count ?? 0}건`;
    document.getElementById("kpi-new").textContent = `${metaData.new_jobs ?? 0}건`;

    const welfareCountEl = document.getElementById("welfare-count");
    if (welfareCountEl) {
      welfareCountEl.textContent = String(allJobs.filter(isWelfarePublicJob).length);
    }

    const wrap = document.getElementById("sources-chips");
    wrap.innerHTML = "";
    (metaData.sources || []).forEach((s) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "source-pill" + (state.sourceId === s.id ? " active" : "");
      btn.dataset.sourceId = s.id;
      btn.title = s.status === "ok" ? `${s.elapsed_sec}초 소요` : `오류: ${s.error}`;
      btn.innerHTML = `<span class="dot ${s.status === "ok" ? "dot-ok" : "dot-err"}"></span>${escapeHtml(s.name)} <strong>${s.count}</strong>`;
      btn.addEventListener("click", () => {
        state.sourceId = state.sourceId === s.id ? "all" : s.id;
        syncUiAndRender();
      });
      wrap.appendChild(btn);
    });
  }

  function getFilteredJobs() {
    const q = state.query.trim().toLowerCase();
    let list = allJobs.filter((job) => {
      const appSt = computeApplicationStatus(job);
      if (state.status === "active" && appSt.code === "closed") return false;
      if (state.status === "closed" && appSt.code !== "closed") return false;

      // 국가/지자체 장애인일자리사업 분리: 기본(OFF)에서는 제외, ON이면 장애인일자리만 따로 모아보기
      const isWelfare = isWelfarePublicJob(job);
      if (state.toggles.welfare_job) {
        if (!isWelfare) return false;
      } else {
        if (isWelfare) return false;
      }

      if (state.worktype === "fulltime" && isPartTimeJob(job)) return false;
      if (state.worktype === "parttime" && !isPartTimeJob(job)) return false;

      if (state.severity !== "all") {
        const sev = job.disability_severity || "상세 확인";
        if (state.severity === "severe_only" && sev !== "중증만 가능") return false;
        if (state.severity === "mild_ok" && sev === "중증만 가능") return false;
      }

      if (state.contract !== "all") {
        const cat = job.contract_category || "상세 참고";
        if (cat !== state.contract) return false;
      }

      if (state.onlyNew && !job.is_new) return false;
      if (state.zone !== "all") {
        if (state.zone === "재택근무") {
          if (!job.is_remote && job.distance_zone !== "재택근무") return false;
        } else if (job.distance_zone !== state.zone) {
          return false;
        }
      }
      // '장애인일자리' 단독 모아보기 모드에서는 복지관 위탁 사업도 함께 보이도록 기관구분 제한 완화
      if (state.org !== "all" && !state.toggles.welfare_job) {
        const o = job.org_type || "민간기업";
        if (state.org === "public" && !["공공기관", "지자체"].includes(o)) return false;
        if (state.org === "major" && !["대기업", "외국계", "표준사업장"].includes(o)) return false;
        if (state.org === "general" && !["민간기업", "복지·비영리"].includes(o)) return false;
      }
      if (state.sourceId !== "all" && !(job.source_ids || []).includes(state.sourceId)) return false;
      if (state.toggles.remote && !job.is_remote) return false;
      if (state.toggles.disabled_only) {
        const dt = job.disability_type || "";
        if (!dt.includes("장애인만") && !dt.includes("제한경쟁")) return false;
      }
      if (state.toggles.hide_restricted && job.residency_restriction) return false;
      if (state.toggles.saved_only && !savedIds.has(job.id)) return false;

      if (q) {
        const hay = [
          job.title,
          job.company,
          job.location,
          job.org_type,
          job.duties,
          job.work_hours,
          job.salary_text,
          job.contract_period,
          job.disability_severity,
          job.disability_detail,
          ...(job.tags || []),
          ...(job.easy_summary || []),
          ...(job.sources || []),
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    list = [...list];
    if (state.sort === "salary_desc") {
      list.sort((a, b) => (b.salary_monthly_krw || 0) - (a.salary_monthly_krw || 0));
    } else if (state.sort === "deadline_asc") {
      list.sort((a, b) => computeApplicationStatus(a).days - computeApplicationStatus(b).days);
    } else if (state.sort === "new_first") {
      list.sort(
        (a, b) =>
          (computeApplicationStatus(a).code === "closed" ? 1 : 0) -
            (computeApplicationStatus(b).code === "closed" ? 1 : 0) ||
          (b.is_new ? 1 : 0) - (a.is_new ? 1 : 0) ||
          String(b.posted_date || b.collected_at || "").localeCompare(String(a.posted_date || a.collected_at || "")) ||
          a.distance_rank - b.distance_rank
      );
    } else {
      list.sort(
        (a, b) =>
          (computeApplicationStatus(a).code === "closed" ? 1 : 0) -
            (computeApplicationStatus(b).code === "closed" ? 1 : 0) ||
          a.distance_rank - b.distance_rank ||
          (b.is_new ? 1 : 0) - (a.is_new ? 1 : 0) ||
          (b.salary_monthly_krw || 0) - (a.salary_monthly_krw || 0)
      );
    }
    return list;
  }

  function renderJobs() {
    const list = getFilteredJobs();
    const container = document.getElementById("job-list");
    const mapSection = document.getElementById("map-view-section");
    const emptyEl = document.getElementById("empty-state");
    const summaryEl = document.getElementById("result-summary");

    summaryEl.textContent = `검색 결과 ${list.length}건 (전체 ${allJobs.length}건)`;

    // 지도 보기 모드일 때는 지도 업데이트
    if (state.view === "map") {
      container.hidden = true;
      emptyEl.hidden = true;
      if (mapSection) mapSection.hidden = false;
      if (window.JobMapView) {
        window.JobMapView.update(list, openModal);
      }
      return;
    }

    if (mapSection) mapSection.hidden = true;
    container.hidden = false;
    container.innerHTML = "";

    if (list.length === 0) {
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;

    const frag = document.createDocumentFragment();
    list.forEach((job) => {
      const appSt = computeApplicationStatus(job);
      const sev = job.disability_severity || "상세 확인";
      const contractText = job.contract_period || job.employment_type || "상세 참고";
      const salDisp = formatSalaryDisplay(job);
      const isPart = isPartTimeJob(job);
      const card = document.createElement("article");
      card.className = "job-card" + (appSt.code === "closed" ? " is-closed" : "");
      const isSaved = savedIds.has(job.id);
      const summaryPreview = (job.easy_summary && job.easy_summary.length)
        ? job.easy_summary.slice(0, 2).join(" ")
        : (job.duties || "");

      card.innerHTML = `
        <div class="card-top">
          <div class="card-badges">
            <span class="badge ${appSt.badgeClass}">${escapeHtml(appSt.badge)}</span>
            <span class="badge ${zoneBadgeClass(job.distance_zone)}">${zoneEmoji(job.distance_zone)}${escapeHtml(job.distance_zone)}</span>
            <span class="badge badge-org">${escapeHtml(job.org_type)}</span>
            <span class="badge badge-other">${isPart ? "⏰ 시간제" : "💼 전일제"}</span>
            <span class="badge ${severityBadgeClass(sev)}">${escapeHtml(sev)}</span>
            ${job.attachment_read ? '<span class="badge badge-att" title="PDF/한글 첨부 공고문까지 AI가 직접 읽고 정리함">📎 첨부분석</span>' : ""}
            ${job.is_new ? '<span class="badge badge-new">NEW</span>' : ""}
          </div>
          <button type="button" class="save-star ${isSaved ? "saved" : ""}" aria-label="관심 공고 저장" aria-pressed="${isSaved}">
            ${isSaved ? "★" : "☆"}
          </button>
        </div>

        <div>
          <p class="card-company">${escapeHtml(job.company)}</p>
          <h2 class="card-title" tabindex="0">${escapeHtml(job.title)}</h2>
        </div>

        <div class="card-facts">
          <div class="fact-item fact-full"><span class="fact-label">💰 급여</span><span class="fact-val">${salDisp.html}</span></div>
          <div class="fact-item fact-full fact-deadline ${appSt.code === "soon" ? "is-soon" : appSt.code === "closed" ? "is-closed" : ""}"><span class="fact-label">📅 마감</span><span class="fact-val">${escapeHtml(appSt.deadlineText)}</span></div>
          <div class="fact-item"><span class="fact-label">⏰ 근무</span><span class="fact-val">${escapeHtml(job.work_hours)}</span></div>
          <div class="fact-item"><span class="fact-label">📄 계약</span><span class="fact-val">${escapeHtml(contractText)}</span></div>
          <div class="fact-item fact-full"><span class="fact-label">📍 지역</span><span class="fact-val">${escapeHtml(job.location)}</span></div>
        </div>

        ${job.residency_restriction ? `<div class="card-warn">⚠️ ${escapeHtml(job.residency_restriction)}</div>` : ""}

        <p class="card-summary">${escapeHtml(summaryPreview)}</p>

        <div class="card-tags">
          ${(job.tags || []).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("")}
        </div>

        <div class="card-footer">
          <div class="source-badges">
            ${(job.sources || []).map((s) => `<span class="src-tag">${escapeHtml(s)}</span>`).join("")}
          </div>
          <div class="card-actions">
            <button type="button" class="detail-btn">상세 요약 보기</button>
            <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer" class="origin-link">원문 ↗</a>
          </div>
        </div>
      `;

      const openDetail = () => openModal(job);
      card.querySelector(".card-title").addEventListener("click", openDetail);
      card.querySelector(".card-title").addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openDetail();
        }
      });
      card.querySelector(".detail-btn").addEventListener("click", openDetail);

      card.querySelector(".save-star").addEventListener("click", () => {
        if (savedIds.has(job.id)) savedIds.delete(job.id);
        else savedIds.add(job.id);
        saveIdsToStorage();
        renderJobs();
      });

      frag.appendChild(card);
    });

    container.appendChild(frag);
  }

  /* 상세 모달 */
  let currentModalJob = null;

  function openModal(job) {
    currentModalJob = job;
    const modal = document.getElementById("job-modal");
    const appSt = computeApplicationStatus(job);
    const sev = job.disability_severity || "상세 확인";

    document.getElementById("modal-badges").innerHTML = `
      <span class="badge ${appSt.badgeClass}">${escapeHtml(appSt.badge)}</span>
      <span class="badge ${zoneBadgeClass(job.distance_zone)}">${zoneEmoji(job.distance_zone)}${escapeHtml(job.distance_zone)}</span>
      <span class="badge badge-org">${escapeHtml(job.org_type)}</span>
      <span class="badge ${severityBadgeClass(sev)}">${escapeHtml(sev)}</span>
      <span class="badge badge-disabled">${escapeHtml(job.disability_type)}</span>
      ${job.attachment_read ? '<span class="badge badge-att">📎 첨부 공고문 분석됨</span>' : ""}
      ${job.is_remote ? '<span class="badge badge-remote">🏠 재택 가능</span>' : ""}
      ${job.is_part_time ? '<span class="badge badge-other">⏰ 단시간</span>' : ""}
    `;
    document.getElementById("modal-title").textContent = job.title;
    document.getElementById("modal-company").textContent = `${job.company} · 출처: ${(job.sources || []).join(", ")}`;

    const warnEl = document.getElementById("modal-warning");
    if (job.residency_restriction) {
      warnEl.hidden = false;
      warnEl.textContent = `⚠️ 거주지 제한 주의: ${job.residency_restriction}`;
    } else {
      warnEl.hidden = true;
    }

    document.getElementById("modal-ai-badge").textContent = job.ai_processed
      ? "✨ DeepSeek 4.1 쉬운 3줄 요약"
      : "📌 핵심 조건 3줄 요약";

    const sumUl = document.getElementById("modal-summary-list");
    sumUl.innerHTML = (job.easy_summary || [])
      .map((line) => `<li>${escapeHtml(line)}</li>`)
      .join("");

    const salDisp = formatSalaryDisplay(job);
    const cells = [
      ["접수 상태 / 기간", `${appSt.badge} · ${appSt.periodText}`],
      ["장애 정도 (중증/경증)", sev + (job.disability_detail ? ` (${job.disability_detail})` : "")],
      ["근무 형태 / 시간", `${isPartTimeJob(job) ? "⏰ 단시간·시간제" : "💼 전일제 (주5일↑)"} · ${job.work_hours}`],
      ["계약 기간 / 고용형태", `${job.contract_period || "상세 참고"} · ${job.employment_type}`],
      ["급여 (예측 연봉 포함)", salDisp.text],
      ["기관 구분", job.org_type],
      ["근무지", `${job.location} (${job.distance_zone})`],
      ["장애 전형", job.disability_type],
    ];
    document.getElementById("modal-detail-grid").innerHTML = cells
      .map(
        ([label, val]) =>
          `<div class="detail-cell"><span class="detail-cell-label">${escapeHtml(label)}</span><span class="detail-cell-val">${escapeHtml(val)}</span></div>`
      )
      .join("");

    document.getElementById("modal-duties").textContent = job.duties || "원문 공고를 참고해 주세요.";
    document.getElementById("modal-qualifications").textContent = job.qualifications || "원문 공고를 참고해 주세요.";
    document.getElementById("modal-apply").textContent = job.apply_method || "아래 원문 공고 링크에서 지원해 주세요.";

    const attSec = document.getElementById("modal-attachments-sec");
    const attList = document.getElementById("modal-attachments-list");
    const atts = Array.isArray(job.attachments) ? job.attachments : [];
    if (attSec && attList) {
      if (atts.length > 0) {
        attSec.hidden = false;
        attList.innerHTML = atts
          .map(
            (a) =>
              `<a href="${escapeHtml(a.url)}" target="_blank" rel="noopener noreferrer" class="att-link"><span>📄 ${escapeHtml(a.name || "첨부파일")}</span><span>다운로드 ↗</span></a>`
          )
          .join("");
      } else {
        attSec.hidden = true;
        attList.innerHTML = "";
      }
    }

    document.getElementById("modal-tags").innerHTML = (job.tags || [])
      .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
      .join("");
    document.getElementById("modal-raw").textContent = job.raw_excerpt || "원문 텍스트가 없습니다.";

    updateModalSaveBtn();

    const linksWrap = document.getElementById("modal-links");
    linksWrap.innerHTML = "";
    const mainA = document.createElement("a");
    mainA.href = job.url;
    mainA.target = "_blank";
    mainA.rel = "noopener noreferrer";
    mainA.className = "origin-link";
    mainA.textContent = "원문 공고에서 지원하기 ↗";
    linksWrap.appendChild(mainA);

    (job.alt_urls || []).forEach((u, i) => {
      const a = document.createElement("a");
      a.href = u;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "detail-btn";
      a.textContent = `다른 출처 #${i + 2} ↗`;
      linksWrap.appendChild(a);
    });

    modal.hidden = false;
    document.body.style.overflow = "hidden";
    document.getElementById("modal-close-btn").focus();
  }

  function updateModalSaveBtn() {
    if (!currentModalJob) return;
    const btn = document.getElementById("modal-save-btn");
    const saved = savedIds.has(currentModalJob.id);
    btn.textContent = saved ? "★ 관심 공고 저장됨" : "☆ 관심 공고 저장";
  }

  function closeModal() {
    document.getElementById("job-modal").hidden = true;
    document.body.style.overflow = "";
    currentModalJob = null;
  }

  /* UI 동기화 */
  function syncUiAndRender() {
    document.querySelectorAll("#zone-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.zone === state.zone);
    });
    document.querySelectorAll("#org-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.org === state.org);
    });
    document.querySelectorAll("#status-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.status === state.status);
    });
    document.querySelectorAll("#worktype-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.worktype === state.worktype);
    });
    document.querySelectorAll("#severity-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.severity === state.severity);
    });
    document.querySelectorAll("#contract-filters .chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.contract === state.contract);
    });
    document.querySelectorAll("#toggle-filters .toggle-chip").forEach((c) => {
      const key = c.dataset.toggle;
      c.setAttribute("aria-pressed", String(Boolean(state.toggles[key])));
    });
    document.querySelectorAll(".kpi-card").forEach((k) => {
      const target = k.dataset.kpi;
      const active =
        (target === "all" && state.zone === "all" && !state.onlyNew) ||
        (target === "new" && state.onlyNew) ||
        (target === state.zone && !state.onlyNew);
      k.classList.toggle("active", active);
    });
    document.querySelectorAll(".source-pill").forEach((p) => {
      p.classList.toggle("active", p.dataset.sourceId === state.sourceId);
    });
    document.getElementById("clear-source-btn").hidden = state.sourceId === "all";

    renderJobs();
  }

  function resetFilters() {
    state.query = "";
    state.zone = "all";
    state.org = "public";
    state.status = "active";
    state.worktype = "fulltime";
    state.severity = "mild_ok";
    state.contract = "all";
    state.sourceId = "all";
    state.sort = "new_first";
    state.onlyNew = false;
    Object.keys(state.toggles).forEach((k) => (state.toggles[k] = false));
    document.getElementById("search-input").value = "";
    document.getElementById("sort-select").value = "new_first";
    syncUiAndRender();
  }

  function bindEvents() {
    document.getElementById("view-list-btn").addEventListener("click", () => {
      state.view = "list";
      document.getElementById("view-list-btn").classList.add("active");
      document.getElementById("view-list-btn").setAttribute("aria-pressed", "true");
      document.getElementById("view-map-btn").classList.remove("active");
      document.getElementById("view-map-btn").setAttribute("aria-pressed", "false");
      renderJobs();
    });

    document.getElementById("view-map-btn").addEventListener("click", () => {
      state.view = "map";
      document.getElementById("view-map-btn").classList.add("active");
      document.getElementById("view-map-btn").setAttribute("aria-pressed", "true");
      document.getElementById("view-list-btn").classList.remove("active");
      document.getElementById("view-list-btn").setAttribute("aria-pressed", "false");
      renderJobs();
      if (window.JobMapView) {
        window.JobMapView.invalidate();
      }
    });

    document.getElementById("search-input").addEventListener("input", (e) => {
      state.query = e.target.value;
      renderJobs();
    });
    document.getElementById("sort-select").addEventListener("change", (e) => {
      state.sort = e.target.value;
      renderJobs();
    });
    document.getElementById("reset-filters-btn").addEventListener("click", resetFilters);
    document.getElementById("empty-reset-btn").addEventListener("click", resetFilters);
    document.getElementById("clear-source-btn").addEventListener("click", () => {
      state.sourceId = "all";
      syncUiAndRender();
    });

    document.querySelectorAll(".kpi-card").forEach((card) => {
      card.addEventListener("click", () => {
        const kpi = card.dataset.kpi;
        if (kpi === "all") {
          state.zone = "all";
          state.onlyNew = false;
        } else if (kpi === "new") {
          state.onlyNew = !state.onlyNew;
          if (state.onlyNew) state.zone = "all";
        } else {
          state.onlyNew = false;
          state.zone = state.zone === kpi ? "all" : kpi;
        }
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#zone-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.onlyNew = false;
        state.zone = btn.dataset.zone;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#org-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.org = btn.dataset.org;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#status-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.status = btn.dataset.status;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#worktype-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.worktype = btn.dataset.worktype;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#severity-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.severity = btn.dataset.severity;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#contract-filters .chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.contract = btn.dataset.contract;
        syncUiAndRender();
      });
    });

    document.querySelectorAll("#toggle-filters .toggle-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.toggle;
        state.toggles[key] = !state.toggles[key];
        syncUiAndRender();
      });
    });

    document.getElementById("modal-close-btn").addEventListener("click", closeModal);
    document.getElementById("job-modal").addEventListener("click", (e) => {
      if (e.target.id === "job-modal") closeModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !document.getElementById("job-modal").hidden) {
        closeModal();
      }
    });
    document.getElementById("modal-save-btn").addEventListener("click", () => {
      if (!currentModalJob) return;
      if (savedIds.has(currentModalJob.id)) savedIds.delete(currentModalJob.id);
      else savedIds.add(currentModalJob.id);
      saveIdsToStorage();
      updateModalSaveBtn();
      renderJobs();
    });
  }

  async function boot() {
    initA11y();
    saveIdsToStorage();
    bindEvents();

    // http(s) 환경(GitHub Pages / 로컬 서버)에서는 최신 JSON을 fetch하고,
    // 로컬 파일 더블클릭(file://) 환경에서는 bundle.js 데이터를 즉시 사용합니다.
    const cacheBust = `?v=${Date.now()}`;
    if (location.protocol !== "file:") {
      try {
        const [jobsRes, metaRes] = await Promise.all([
          fetch(`./data/jobs.json${cacheBust}`),
          fetch(`./data/meta.json${cacheBust}`),
        ]);
        if (jobsRes.ok) {
          allJobs = await jobsRes.json();
          if (metaRes.ok) metaData = await metaRes.json();
          renderMeta();
          syncUiAndRender();
          return;
        }
      } catch (err) {
        console.warn("fetch 실패, bundle.js 폴백 사용:", err);
      }
    }

    if (Array.isArray(window.__JOBS_DATA__)) {
      allJobs = window.__JOBS_DATA__;
      metaData = window.__META_DATA__ || null;
      renderMeta();
      syncUiAndRender();
      return;
    }

    document.getElementById("result-summary").textContent =
      "아직 수집된 공고 데이터가 없습니다. 먼저 '공고_지금수집하기.bat'을 실행해 주세요.";
  }

  window.formatSalaryDisplay = formatSalaryDisplay;
  window.computeApplicationStatus = computeApplicationStatus;
  boot();
})();
