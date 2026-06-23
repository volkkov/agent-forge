/* Agent Forge — app logic */

(function () {
  const state = {
    repos: [],
    categories: [],
    i18n: null,
    lang: localStorage.getItem("af-lang") || "en",
    zoom: parseInt(localStorage.getItem("af-zoom") || "100", 10),
    activeCategory: "all",
    query: "",
  };

  const els = {};

  function cacheEls() {
    els.rail = document.getElementById("category-rail");
    els.feed = document.getElementById("feed");
    els.noResults = document.getElementById("no-results");
    els.searchInput = document.getElementById("search-input");
    els.langToggle = document.getElementById("lang-toggle");
    els.zoomIn = document.getElementById("zoom-in");
    els.zoomOut = document.getElementById("zoom-out");
    els.zoomLevel = document.getElementById("zoom-level");
    els.statUseful = document.getElementById("stat-useful");
    els.statWatch = document.getElementById("stat-watch");
    els.statCategories = document.getElementById("stat-categories");
    els.transparencyToggle = document.getElementById("transparency-toggle");
    els.transparencyBody = document.getElementById("transparency-body");
    els.researchFeed = document.getElementById("research-feed");
    els.lastUpdated = document.getElementById("last-updated-time");
    els.detailOverlay = document.getElementById("signal-detail");
    els.detailCard = document.getElementById("signal-detail-card");
  }

  // ---------- i18n ----------

  function t(key) {
    const dict = state.i18n.ui[state.lang] || state.i18n.ui.en;
    return dict[key] || key;
  }

  function applyStaticI18n() {
    document.documentElement.setAttribute("data-lang", state.lang);
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
    });
  }

  function categoryLabel(cat) {
    return state.lang === "ru" ? cat.ru : cat.en;
  }

  function repoSummary(repo) {
    return state.lang === "ru" ? repo.summary_ru : repo.summary_en;
  }

  function repoReason(repo) {
    return state.lang === "ru" ? repo.verdict_reason_ru : repo.verdict_reason_en;
  }

  // ---------- zoom ----------

  function applyZoom() {
    document.documentElement.style.fontSize = state.zoom + "%";
    els.zoomLevel.textContent = state.zoom + "%";
  }

  function setZoom(delta) {
    state.zoom = Math.min(140, Math.max(80, state.zoom + delta));
    localStorage.setItem("af-zoom", state.zoom);
    applyZoom();
  }

  // ---------- pulse sparkline ----------

  function pulseSVG(health) {
    const seeds = {
      active: [10, 16, 22, 14, 26, 18],
      stale: [18, 14, 10, 8, 6, 5],
      dead: [4, 3, 4, 3, 3, 2],
    };
    const heights = seeds[health] || seeds.stale;
    return heights
      .map((h) => `<span class="bar" style="height:${h}px"></span>`)
      .join("");
  }

  // ---------- rendering ----------

  function getFilteredRepos() {
    const q = state.query.trim().toLowerCase();
    return state.repos.filter((r) => {
      if (r.verdict !== "useful") return false;
      if (state.activeCategory !== "all" && r.category !== state.activeCategory) return false;
      if (!q) return true;
      const haystack = [r.name, repoSummary(r), r.owner, ...(r.tags || [])]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }

  function renderCategoryRail() {
    const counts = {};
    state.repos.forEach((r) => {
      if (r.verdict !== "useful") return;
      counts[r.category] = (counts[r.category] || 0) + 1;
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);

    const usedCategories = state.categories.filter((c) => counts[c.id]);

    let html = `<button class="cat-chip ${state.activeCategory === "all" ? "active" : ""}" data-cat="all">
      ${t("filter_all")} <span class="count">${total}</span>
    </button>`;

    usedCategories.forEach((cat) => {
      html += `<button class="cat-chip ${state.activeCategory === cat.id ? "active" : ""}" data-cat="${cat.id}">
        ${categoryLabel(cat)} <span class="count">${counts[cat.id]}</span>
      </button>`;
    });

    els.rail.innerHTML = html;
    els.rail.querySelectorAll(".cat-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.activeCategory = btn.getAttribute("data-cat");
        render();
      });
    });
  }

  function rowHTML(repo) {
    const stars = repo.stars >= 1000 ? (repo.stars / 1000).toFixed(1) + "k" : repo.stars;
    return `
      <article class="signal-row" data-health="${repo.health}" data-id="${repo.id}" tabindex="0" role="button" aria-label="${repo.name}">
        <div class="signal-pulse" aria-hidden="true">${pulseSVG(repo.health)}</div>
        <div class="row-main">
          <div class="row-title-line">
            <span class="row-name">${repo.name}</span>
            <span class="row-owner">${repo.owner}</span>
          </div>
          <p class="row-summary">${repoSummary(repo)}</p>
          <div class="row-tags">${(repo.tags || []).slice(0, 4).map((tg) => `<span class="row-tag">${tg}</span>`).join("")}</div>
        </div>
        <div class="row-meta">
          <span class="row-stars">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14l-5-4.87 6.91-1.01z"/></svg>
            ${stars}
          </span>
          <span class="row-health-badge">${t("health_" + repo.health)}</span>
        </div>
        <svg class="row-arrow" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </article>`;
  }

  function renderFeed() {
    const repos = getFilteredRepos();
    if (repos.length === 0) {
      els.feed.innerHTML = "";
      els.noResults.hidden = false;
      return;
    }
    els.noResults.hidden = true;
    els.feed.innerHTML = repos.map(rowHTML).join("");
    els.feed.querySelectorAll(".signal-row").forEach((row) => {
      const open = () => openDetail(row.getAttribute("data-id"));
      row.addEventListener("click", open);
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
  }

  function renderStats() {
    const useful = state.repos.filter((r) => r.verdict === "useful").length;
    const watch = state.repos.filter((r) => r.verdict === "hype").length;
    const cats = new Set(state.repos.filter((r) => r.verdict === "useful").map((r) => r.category)).size;
    animateNumber(els.statUseful, useful);
    animateNumber(els.statWatch, watch);
    animateNumber(els.statCategories, cats);
  }

  function animateNumber(el, target) {
    let current = 0;
    const step = Math.max(1, Math.ceil(target / 24));
    const tick = () => {
      current = Math.min(target, current + step);
      el.textContent = current;
      if (current < target) requestAnimationFrame(tick);
    };
    tick();
  }

  function renderTransparency() {
    const flagged = state.repos.filter((r) => r.verdict === "hype" || r.verdict === "broken");
    if (flagged.length === 0) {
      document.getElementById("transparency").style.display = "none";
      return;
    }
    els.transparencyBody.innerHTML = flagged
      .map(
        (r) => `
      <div class="transparency-item">
        <span class="t-name">${r.name}</span>
        <span class="t-verdict-tag ${r.verdict}">${t("verdict_" + r.verdict)}</span>
        <span class="t-reason">${repoReason(r)}</span>
      </div>`
      )
      .join("");
  }

  function renderResearch() {
    const research = state.repos.filter((r) => r.source !== "manual-seed" && r.verdict === "useful");
    const section = document.getElementById("research-section");
    if (research.length === 0) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";
    els.researchFeed.innerHTML = `<div class="feed">${research.map(rowHTML).join("")}</div>`;
  }

  function renderLastUpdated() {
    const dates = state.repos.map((r) => r.last_checked).filter(Boolean).sort();
    const latest = dates[dates.length - 1];
    els.lastUpdated.textContent = latest || "—";
  }

  function render() {
    renderCategoryRail();
    renderFeed();
    renderStats();
    renderTransparency();
    renderResearch();
    renderLastUpdated();
  }

  // ---------- detail overlay ----------

  function openDetail(id) {
    const repo = state.repos.find((r) => r.id === id);
    if (!repo) return;
    const stars = repo.stars >= 1000 ? (repo.stars / 1000).toFixed(1) + "k" : repo.stars;
    const lastCommit = (repo.last_commit_at || "").slice(0, 10);

    els.detailCard.innerHTML = `
      <button class="detail-close" id="detail-close" aria-label="Close">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round"/></svg>
      </button>
      <h2 class="detail-name">${repo.name}</h2>
      <p class="detail-owner">${repo.owner} · ${repo.id}</p>
      <p class="detail-summary">${repoSummary(repo)}</p>
      <div class="detail-reason">${repoReason(repo)}</div>
      <div class="detail-stat-grid">
        <div class="detail-stat"><span class="detail-stat-val">${stars}</span><span class="detail-stat-label">${t("stars")}</span></div>
        <div class="detail-stat"><span class="detail-stat-val">${repo.forks}</span><span class="detail-stat-label">forks</span></div>
        <div class="detail-stat"><span class="detail-stat-val">${lastCommit}</span><span class="detail-stat-label">${t("last_commit")}</span></div>
      </div>
      ${(repo.risk_flags || []).length ? `<div class="row-tags" style="margin-bottom:20px;">${repo.risk_flags.map((f) => `<span class="row-tag">⚠ ${f}</span>`).join("")}</div>` : ""}
      <a class="detail-cta" href="${repo.url}" target="_blank" rel="noopener">
        ${t("view_on_github")}
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17L17 7M7 7h10v10" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </a>
    `;
    els.detailOverlay.hidden = false;
    document.body.style.overflow = "hidden";
    document.getElementById("detail-close").addEventListener("click", closeDetail);
  }

  function closeDetail() {
    els.detailOverlay.hidden = true;
    document.body.style.overflow = "";
  }

  // ---------- event wiring ----------

  function wireEvents() {
    els.searchInput.addEventListener("input", (e) => {
      state.query = e.target.value;
      renderFeed();
    });

    els.langToggle.addEventListener("click", () => {
      state.lang = state.lang === "en" ? "ru" : "en";
      localStorage.setItem("af-lang", state.lang);
      applyStaticI18n();
      render();
    });

    els.zoomIn.addEventListener("click", () => setZoom(10));
    els.zoomOut.addEventListener("click", () => setZoom(-10));

    els.transparencyToggle.addEventListener("click", () => {
      const expanded = els.transparencyToggle.getAttribute("aria-expanded") === "true";
      els.transparencyToggle.setAttribute("aria-expanded", String(!expanded));
      els.transparencyBody.hidden = expanded;
    });

    els.detailOverlay.addEventListener("click", (e) => {
      if (e.target === els.detailOverlay) closeDetail();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !els.detailOverlay.hidden) closeDetail();
    });
  }

  // ---------- boot ----------

  function boot() {
    const data = window.AgentForgeData;
    state.repos = data.repos;
    state.categories = data.i18n.categories;
    state.i18n = data.i18n;

    cacheEls();
    applyZoom();
    applyStaticI18n();
    wireEvents();
    render();
  }

  if (window.AgentForgeData) {
    boot();
  } else {
    window.addEventListener("agentforge:data-ready", boot);
    window.addEventListener("agentforge:data-error", () => {
      document.getElementById("feed").innerHTML =
        '<p style="text-align:center;color:#9A9CAA;padding:40px;">Could not load data. Check the console for details.</p>';
    });
  }
})();
