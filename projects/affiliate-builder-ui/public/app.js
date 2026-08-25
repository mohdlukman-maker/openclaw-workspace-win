const state = {
  selected: null,
};

const el = (id) => document.getElementById(id);

function setBusy(button, busy) {
  button.disabled = busy;
}

function setMessage(text, isError = false) {
  el("message").textContent = text;
  el("message").style.color = isError ? "#b42318" : "#666b74";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    const site = status.site?.site_url || "No Netlify site linked";
    const token = status.hasNetlifyToken ? "Netlify token ready" : "Netlify token not in server env";
    el("status").textContent = `${site} · ${token}`;
  } catch (error) {
    el("status").textContent = error.message;
  }
}

function selectedPeriod() {
  return document.querySelector("input[name='period']:checked")?.value || "week";
}

function renderResults(results) {
  const box = el("results");
  box.innerHTML = "";
  if (!results.length) {
    box.innerHTML = `<div class="message">No Shopee results found. Paste a product link instead.</div>`;
    return;
  }

  results.forEach((result) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result";
    button.innerHTML = `<strong>${result.title}</strong><span>${result.snippet || result.url}</span>`;
    button.addEventListener("click", () => {
      state.selected = result;
      el("productUrl").value = result.url;
      el("productTitle").value = result.title;
      document.querySelectorAll(".result").forEach((node) => node.classList.remove("is-selected"));
      button.classList.add("is-selected");
    });
    box.appendChild(button);
  });
}

el("searchBtn").addEventListener("click", async () => {
  const button = el("searchBtn");
  setBusy(button, true);
  setMessage("Searching Shopee results...");
  try {
    const data = await api(`/api/search?category=${encodeURIComponent(el("category").value)}&period=${selectedPeriod()}`);
    renderResults(data.results);
    setMessage(`Search complete. Query: ${data.query}`);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

el("generateBtn").addEventListener("click", async () => {
  const button = el("generateBtn");
  setBusy(button, true);
  setMessage("Generating page and downloading product images...");
  try {
    const data = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        category: el("category").value,
        productUrl: el("productUrl").value,
        title: el("productTitle").value,
        affiliateUrl: el("affiliateUrl").value,
        selectedUrl: state.selected?.url,
        selectedTitle: state.selected?.title,
      }),
    });
    el("preview").src = `${data.previewUrl}?t=${Date.now()}`;
    setMessage(`Generated. Images saved: ${data.imageCount}. Review preview before publishing.`);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

el("refreshPreviewBtn").addEventListener("click", () => {
  el("preview").src = `/preview/?t=${Date.now()}`;
});

el("publishBtn").addEventListener("click", async () => {
  const button = el("publishBtn");
  const ok = confirm("Publish the generated page to the production Netlify URL?");
  if (!ok) return;
  setBusy(button, true);
  setMessage("Publishing to Netlify production...");
  try {
    const data = await api("/api/publish", { method: "POST", body: "{}" });
    setMessage(`Published: ${data.url || data.deploy_url || "Netlify deploy complete"}`);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

loadStatus();
