/* Agent Forge — data loader
   Fetches the repo dataset and i18n strings produced by the
   GitHub Action pipeline (../data/repos.json, ../data/i18n.json)
   and exposes them on window.AgentForgeData.
*/

(function () {
  async function loadJSON(path) {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
    return res.json();
  }

  async function init() {
    const [repos, i18n] = await Promise.all([
      loadJSON("../data/repos.json"),
      loadJSON("../data/i18n.json"),
    ]);
    window.AgentForgeData = { repos, i18n };
    window.dispatchEvent(new CustomEvent("agentforge:data-ready"));
  }

  init().catch((err) => {
    console.error("Agent Forge: data load failed", err);
    window.dispatchEvent(new CustomEvent("agentforge:data-error", { detail: err }));
  });
})();
