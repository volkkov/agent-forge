/* Agent Forge — data loader
   Fetches the repo dataset and i18n strings produced by the
   GitHub Action pipeline. Tries several candidate paths because
   hosting setups differ: GitHub Pages serves from the repo root
   (site/ + ../data/ works), while some platforms (e.g. Vercel with
   "site" set as the project root) serve site/ as the web root, so
   ../data/ would resolve outside the deployed files. Falling back
   through candidates means the same code works either way without
   per-host configuration.
*/

(function () {
  const CANDIDATE_BASES = ["./data", "data", "../data", "/data"];

  async function tryLoadJSON(filename) {
    let lastErr;
    for (const base of CANDIDATE_BASES) {
      try {
        const res = await fetch(`${base}/${filename}`, { cache: "no-store" });
        if (res.ok) return await res.json();
        lastErr = new Error(`${base}/${filename}: HTTP ${res.status}`);
      } catch (err) {
        lastErr = err;
      }
    }
    throw lastErr;
  }

  async function init() {
    const [repos, i18n] = await Promise.all([
      tryLoadJSON("repos.json"),
      tryLoadJSON("i18n.json"),
    ]);
    window.AgentForgeData = { repos, i18n };
    window.dispatchEvent(new CustomEvent("agentforge:data-ready"));
  }

  init().catch((err) => {
    console.error("Agent Forge: data load failed", err);
    window.dispatchEvent(new CustomEvent("agentforge:data-error", { detail: err }));
  });
})();
