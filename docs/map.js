(() => {
  "use strict";

  // 고양시 중심 기준 좌표 (고양특례시청 / 화정·일산 중간)
  const GOYANG_HOME = { lat: 37.6584, lng: 126.832, label: "고양시 기준점" };

  // 고양시 동별 + 서울 25개구 + 경기도 31개시/군 + 인천 주요 지역 좌표 사전
  // 구체적인 동/업무지구가 상위에 오도록 정렬 (먼저 매칭되는 가장 정밀한 좌표 사용)
  const KOREA_GEO = [
    // --- 고양시 세부 지역 ---
    ["삼송", 37.6531, 126.8955, "고양 삼송"],
    ["원흥", 37.6505, 126.8732, "고양 원흥"],
    ["향동", 37.6022, 126.8902, "고양 향동"],
    ["덕은", 37.5844, 126.8781, "고양 덕은"],
    ["화정", 37.6346, 126.8326, "고양 화정"],
    ["행신", 37.6121, 126.8342, "고양 행신"],
    ["능곡", 37.6186, 126.8211, "고양 능곡"],
    ["백석", 37.6431, 126.7879, "고양 백석"],
    ["마두", 37.6522, 126.7776, "고양 마두"],
    ["정발산", 37.6594, 126.7734, "고양 정발산"],
    ["장항", 37.6562, 126.7662, "고양 장항동"],
    ["풍동", 37.6656, 126.7988, "고양 풍동"],
    ["식사", 37.6777, 126.8124, "고양 식사동"],
    ["주엽", 37.6701, 126.7612, "고양 주엽"],
    ["대화", 37.6761, 126.7475, "고양 대화"],
    ["탄현", 37.6937, 126.7611, "고양 탄현"],
    ["중산", 37.6881, 126.7797, "고양 중산"],
    ["일산서구", 37.6752, 126.7506, "고양 일산서구"],
    ["일산동구", 37.6587, 126.7749, "고양 일산동구"],
    ["덕양구", 37.6375, 126.8321, "고양 덕양구"],
    ["일산", 37.664, 126.768, "고양 일산"],
    ["고양", 37.6584, 126.832, "고양시"],

    // --- 서울 주요 업무지구 & 25개 자치구 ---
    ["상암", 37.5791, 126.8895, "서울 상암DMC"],
    ["마곡", 37.5602, 126.8255, "서울 마곡"],
    ["여의도", 37.5219, 126.9245, "서울 여의도"],
    ["광화문", 37.5716, 126.9769, "서울 광화문"],
    ["공덕", 37.5432, 126.9516, "서울 공덕"],
    ["은평", 37.6027, 126.9291, "서울 은평구"],
    ["마포", 37.5663, 126.9019, "서울 마포구"],
    ["서대문", 37.5791, 126.9368, "서울 서대문구"],
    ["강서", 37.5509, 126.8495, "서울 강서구"],
    ["양천", 37.517, 126.8664, "서울 양천구"],
    ["영등포", 37.5264, 126.8962, "서울 영등포구"],
    ["종로", 37.573, 126.9794, "서울 종로구"],
    ["중구", 37.5641, 126.9979, "서울 중구"],
    ["용산", 37.5326, 126.9905, "서울 용산구"],
    ["성동", 37.5633, 127.0369, "서울 성동구"],
    ["광진", 37.5385, 127.0823, "서울 광진구"],
    ["동대문", 37.5744, 127.0396, "서울 동대문구"],
    ["중랑", 37.6066, 127.0927, "서울 중랑구"],
    ["성북", 37.5894, 127.0167, "서울 성북구"],
    ["강북", 37.6396, 127.0257, "서울 강북구"],
    ["도봉", 37.6688, 127.0471, "서울 도봉구"],
    ["노원", 37.6542, 127.0568, "서울 노원구"],
    ["구로", 37.4954, 126.8874, "서울 구로구"],
    ["금천", 37.4569, 126.8955, "서울 금천구"],
    ["동작", 37.5124, 126.9393, "서울 동작구"],
    ["관악", 37.4784, 126.9516, "서울 관악구"],
    ["서초", 37.4837, 127.0324, "서울 서초구"],
    ["강남", 37.5172, 127.0473, "서울 강남구"],
    ["송파", 37.5145, 127.1059, "서울 송파구"],
    ["강동", 37.5301, 127.1238, "서울 강동구"],

    // --- 경기도 주요 시/군 ---
    ["판교", 37.3948, 127.1112, "성남 판교"],
    ["분당", 37.3827, 127.1189, "성남 분당"],
    ["파주", 37.7599, 126.7802, "경기 파주시"],
    ["김포", 37.6152, 126.7156, "경기 김포시"],
    ["양주", 37.7853, 127.0458, "경기 양주시"],
    ["의정부", 37.7381, 127.0337, "경기 의정부시"],
    ["동두천", 37.9035, 127.0605, "경기 동두천시"],
    ["포천", 37.8949, 127.2003, "경기 포천시"],
    ["연천", 38.0966, 127.075, "경기 연천군"],
    ["남양주", 37.636, 127.2165, "경기 남양주시"],
    ["구리", 37.5943, 127.1295, "경기 구리시"],
    ["하남", 37.5393, 127.2149, "경기 하남시"],
    ["부천", 37.5034, 126.766, "경기 부천시"],
    ["광명", 37.4786, 126.8644, "경기 광명시"],
    ["시흥", 37.38, 126.8029, "경기 시흥시"],
    ["안산", 37.3219, 126.8309, "경기 안산시"],
    ["안양", 37.3943, 126.9568, "경기 안양시"],
    ["과천", 37.4292, 126.9876, "경기 과천시"],
    ["군포", 37.3617, 126.9352, "경기 군포시"],
    ["의왕", 37.3449, 126.9683, "경기 의왕시"],
    ["성남", 37.4201, 127.1262, "경기 성남시"],
    ["수원", 37.2636, 127.0286, "경기 수원시"],
    ["용인", 37.2411, 127.1775, "경기 용인시"],
    ["화성", 37.1995, 126.8312, "경기 화성시"],
    ["오산", 37.1498, 127.0772, "경기 오산시"],
    ["평택", 36.9921, 127.1129, "경기 평택시"],
    ["안성", 37.0079, 127.2797, "경기 안성시"],
    ["이천", 37.2723, 127.435, "경기 이천시"],
    ["여주", 37.2983, 127.6374, "경기 여주시"],
    ["양평", 37.4917, 127.4876, "경기 양평군"],
    ["가평", 37.8315, 127.5096, "경기 가평군"],
    ["경기도 광주", 37.4294, 127.2551, "경기 광주시"],
    ["경기 광주", 37.4294, 127.2551, "경기 광주시"],

    // --- 인천 ---
    ["송도", 37.3916, 126.6495, "인천 송도"],
    ["부평", 37.5074, 126.7219, "인천 부평구"],
    ["계양", 37.5374, 126.7377, "인천 계양구"],
    ["인천", 37.4563, 126.7052, "인천광역시"],

    // --- 광역 폴백 ---
    ["서울", 37.5665, 126.978, "서울특별시"],
    ["경기", 37.4138, 127.5183, "경기도"],
  ];

  function haversineKm(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function resolveJobCoords(job) {
    const loc = (job.location || "").trim();
    const title = (job.title || "").trim();

    // 순수 재택/지역무관(특정 근무지 주소 없음)인 경우 지도에 찍지 않고 재택 패널로 분류
    if (
      (job.distance_zone === "재택근무" || job.is_remote) &&
      (!loc || /^(재택|원격|지역무관|전국|상세\s*참고|미상)/.test(loc))
    ) {
      return null;
    }

    for (const [kw, lat, lng, label] of KOREA_GEO) {
      if (loc.includes(kw)) {
        return { lat, lng, label };
      }
    }
    for (const [kw, lat, lng, label] of KOREA_GEO) {
      if (title.includes(kw)) {
        return { lat, lng, label };
      }
    }
    if (job.is_remote) return null;
    return null;
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  let mapInstance = null;
  let markerLayer = null;
  let homeLayer = null;
  let lastGroups = [];
  let lastRemoteJobs = [];
  let selectedGroupKey = null;
  let openModalCb = null;

  function ensureMap() {
    if (mapInstance) return true;
    if (typeof window.L === "undefined") {
      const canvas = document.getElementById("job-map-canvas");
      if (canvas) {
        canvas.innerHTML =
          '<div class="map-offline">지도 라이브러리(Leaflet)를 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 새로고침해 주세요. (우측 지역별 목록은 정상 이용 가능합니다.)</div>';
      }
      return false;
    }

    mapInstance = L.map("job-map-canvas", {
      center: [37.61, 126.91],
      zoom: 11,
      zoomControl: true,
    });

    // 한국어 지명이 선명한 오픈스트리트맵 한국(OSM-KR) 타일 (API 키 불필요) + OSM 공식 폴백
    const osmKr = L.tileLayer("https://tiles.osm.kr/hot/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors &copy; OSM Korea",
    });
    osmKr.on("tileerror", () => {
      if (!mapInstance._osmFallbackAdded) {
        mapInstance._osmFallbackAdded = true;
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 18,
          attribution: "&copy; OpenStreetMap contributors",
        }).addTo(mapInstance);
      }
    });
    osmKr.addTo(mapInstance);

    homeLayer = L.layerGroup().addTo(mapInstance);
    markerLayer = L.layerGroup().addTo(mapInstance);

    // 고양시 기준점 + 출퇴근 반경 원 (10km, 20km)
    L.circle([GOYANG_HOME.lat, GOYANG_HOME.lng], {
      radius: 10000,
      color: "#0d7a5f",
      weight: 1.5,
      dashArray: "6 6",
      fillColor: "#0d7a5f",
      fillOpacity: 0.05,
    }).addTo(homeLayer);

    L.circle([GOYANG_HOME.lat, GOYANG_HOME.lng], {
      radius: 20000,
      color: "#0f4c81",
      weight: 1.2,
      dashArray: "4 6",
      fillColor: "#0f4c81",
      fillOpacity: 0.02,
    }).addTo(homeLayer);

    const homeIcon = L.divIcon({
      className: "map-pin-wrap",
      html: '<div class="map-home-pin" title="고양시 기준점">🏠 고양시</div>',
      iconSize: [78, 28],
      iconAnchor: [39, 14],
    });
    L.marker([GOYANG_HOME.lat, GOYANG_HOME.lng], { icon: homeIcon, zIndexOffset: 500 })
      .bindPopup("<strong>🏠 고양시 기준점</strong><br/>초록 점선: 반경 10km<br/>파랑 점선: 반경 20km")
      .addTo(homeLayer);

    const homeBtn = document.getElementById("map-focus-goyang");
    if (homeBtn) {
      homeBtn.addEventListener("click", () => {
        mapInstance.setView([GOYANG_HOME.lat, GOYANG_HOME.lng], 12);
      });
    }
    const fitBtn = document.getElementById("map-fit-all");
    if (fitBtn) {
      fitBtn.addEventListener("click", () => fitAllMarkers());
    }
    const showRemoteBtn = document.getElementById("map-show-remote");
    if (showRemoteBtn) {
      showRemoteBtn.addEventListener("click", () => {
        selectedGroupKey = "__remote__";
        renderSidePanel();
      });
    }
    const showAllBtn = document.getElementById("map-show-all-regions");
    if (showAllBtn) {
      showAllBtn.addEventListener("click", () => {
        selectedGroupKey = null;
        renderSidePanel();
      });
    }

    return true;
  }

  function fitAllMarkers() {
    if (!mapInstance || !lastGroups.length) return;
    const pts = [[GOYANG_HOME.lat, GOYANG_HOME.lng]];
    lastGroups.forEach((g) => pts.push([g.lat, g.lng]));
    mapInstance.fitBounds(pts, { padding: [36, 36], maxZoom: 12 });
  }

  function groupZoneColorClass(group) {
    const hasGoyang = group.jobs.some((j) => j.distance_zone === "고양시 관내");
    if (hasGoyang) return "pin-goyang";
    const hasNearby = group.jobs.some((j) => j.distance_zone === "인접 출퇴근");
    if (hasNearby) return "pin-nearby";
    return "pin-other";
  }

  function renderSidePanel() {
    const titleEl = document.getElementById("map-panel-title");
    const listEl = document.getElementById("map-panel-list");
    const remoteBtn = document.getElementById("map-show-remote");
    const showAllBtn = document.getElementById("map-show-all-regions");
    if (!listEl || !titleEl) return;

    if (remoteBtn) {
      remoteBtn.textContent = `🟣 재택·지역무관 (${lastRemoteJobs.length}건)`;
      remoteBtn.classList.toggle("active", selectedGroupKey === "__remote__");
    }
    if (showAllBtn) {
      showAllBtn.hidden = selectedGroupKey === null;
    }

    listEl.innerHTML = "";

    // 1) 재택 공고 보기
    if (selectedGroupKey === "__remote__") {
      titleEl.textContent = `🟣 재택·지역무관 공고 (${lastRemoteJobs.length}건)`;
      if (!lastRemoteJobs.length) {
        listEl.innerHTML = '<p class="map-empty">현재 필터 조건에 해당하는 재택/지역무관 공고가 없습니다.</p>';
        return;
      }
      renderJobItemsInto(listEl, lastRemoteJobs);
      return;
    }

    // 2) 특정 지역 핀 클릭한 경우
    if (selectedGroupKey) {
      const grp = lastGroups.find((g) => g.key === selectedGroupKey);
      if (grp) {
        titleEl.textContent = `📍 ${grp.label} (${grp.jobs.length}건 · 고양에서 약 ${grp.distKm.toFixed(1)}km)`;
        renderJobItemsInto(listEl, grp.jobs);
        return;
      }
    }

    // 3) 기본: 전체 지역 요약 리스트 (거리순 정렬 → 클릭 시 지도 이동 + 상세 펼치기)
    const totalMapped = lastGroups.reduce((acc, g) => acc + g.jobs.length, 0);
    titleEl.textContent = `🗺️ 지역별 공고 분포 (${totalMapped}건 · 클릭하여 확대)`;

    if (!lastGroups.length && !lastRemoteJobs.length) {
      listEl.innerHTML = '<p class="map-empty">표시할 공고가 없습니다. 필터를 조정해 보세요.</p>';
      return;
    }

    lastGroups.forEach((g) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `map-region-row ${groupZoneColorClass(g)}`;
      row.innerHTML = `
        <div class="map-region-main">
          <strong>${escapeHtml(g.label)}</strong>
          <span class="map-region-dist">고양시에서 약 ${g.distKm.toFixed(1)}km</span>
        </div>
        <span class="map-region-cnt">${g.jobs.length}건</span>
      `;
      row.addEventListener("click", () => {
        selectedGroupKey = g.key;
        if (mapInstance) {
          mapInstance.setView([g.lat, g.lng], 13);
        }
        renderSidePanel();
      });
      listEl.appendChild(row);
    });
  }

  function renderJobItemsInto(container, jobs) {
    jobs.forEach((job) => {
      const item = document.createElement("div");
      item.className = "map-job-item";
      item.innerHTML = `
        <div class="map-job-top">
          <span class="badge badge-org">${escapeHtml(job.org_type)}</span>
          <span class="badge badge-other">${escapeHtml(job.disability_severity || "상세 확인")}</span>
        </div>
        <div class="map-job-company">${escapeHtml(job.company)}</div>
        <div class="map-job-title">${escapeHtml(job.title)}</div>
        <div class="map-job-meta">
          <span>💰 ${window.formatSalaryDisplay ? window.formatSalaryDisplay(job).html : escapeHtml(job.salary_text)}</span><br/>
          <span>📅 마감: ${window.computeApplicationStatus ? escapeHtml(window.computeApplicationStatus(job).deadlineText) : escapeHtml(job.deadline || "채용시까지")}</span><br/>
          <span>⏰ ${escapeHtml(job.work_hours)}</span>
        </div>
      `;
      item.addEventListener("click", () => {
        if (typeof openModalCb === "function") openModalCb(job);
      });
      container.appendChild(item);
    });
  }

  function update(filteredJobs, onOpenModal) {
    openModalCb = onOpenModal;
    const ready = ensureMap();

    const groupMap = new Map();
    const remoteList = [];

    filteredJobs.forEach((job) => {
      const geo = resolveJobCoords(job);
      if (!geo) {
        remoteList.push(job);
        return;
      }
      const key = geo.label;
      if (!groupMap.has(key)) {
        groupMap.set(key, {
          key,
          label: geo.label,
          lat: geo.lat,
          lng: geo.lng,
          distKm: haversineKm(GOYANG_HOME.lat, GOYANG_HOME.lng, geo.lat, geo.lng),
          jobs: [],
        });
      }
      groupMap.get(key).jobs.push(job);
    });

    lastGroups = [...groupMap.values()].sort((a, b) => a.distKm - b.distKm);
    lastRemoteJobs = remoteList;

    if (selectedGroupKey && selectedGroupKey !== "__remote__" && !groupMap.has(selectedGroupKey)) {
      selectedGroupKey = null;
    }

    if (ready && markerLayer) {
      markerLayer.clearLayers();
      lastGroups.forEach((g) => {
        const cls = groupZoneColorClass(g);
        const icon = L.divIcon({
          className: "map-pin-wrap",
          html: `<div class="map-cluster-pin ${cls}" title="${escapeHtml(g.label)} (${g.jobs.length}건 · 약 ${g.distKm.toFixed(1)}km)"><span class="pin-name">${escapeHtml(g.label.replace(/^(고양|서울|경기)\s+/, ""))}</span><span class="pin-cnt">${g.jobs.length}</span></div>`,
          iconSize: [null, null],
          iconAnchor: [32, 13],
        });
        const m = L.marker([g.lat, g.lng], { icon, riseOnHover: true });
        m.on("click", () => {
          selectedGroupKey = g.key;
          renderSidePanel();
        });
        m.addTo(markerLayer);
      });

      setTimeout(() => {
        if (mapInstance) mapInstance.invalidateSize();
      }, 60);
    }

    renderSidePanel();
  }

  window.JobMapView = {
    update,
    invalidate: () => {
      if (mapInstance) {
        setTimeout(() => mapInstance.invalidateSize(), 60);
      }
    },
    fitAll: fitAllMarkers,
  };
})();
