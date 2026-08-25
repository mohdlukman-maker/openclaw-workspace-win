const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const root = __dirname;
const workspace = path.resolve(root, "..", "..");
const publicDir = path.join(root, "public");
const generatedDir = path.join(root, "generated", "site");
const siteConfigPath = path.join(workspace, "scripts", "netlify-site.local.json");

const mime = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, { "Content-Type": type });
  res.end(type.includes("json") ? JSON.stringify(body, null, 2) : body);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 2_000_000) {
        req.destroy();
        reject(new Error("Request body too large"));
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(error);
      }
    });
  });
}

function safeText(value, fallback = "") {
  return String(value || fallback)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function safeFileName(value) {
  return String(value || "product")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "product";
}

function decodeDuckUrl(url) {
  try {
    if (!url.includes("duckduckgo.com/l/")) return url;
    const parsed = new URL(url.startsWith("//") ? `https:${url}` : url);
    return parsed.searchParams.get("uddg") || url;
  } catch {
    return url;
  }
}

async function fetchText(url, headers = {}) {
  const response = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "accept-language": "ms-MY,ms;q=0.9,en;q=0.8",
      ...headers,
    },
  });
  if (!response.ok) throw new Error(`Fetch failed ${response.status}: ${url}`);
  return response.text();
}

async function searchWeb(category, period) {
  const periodWords = {
    day: "today yesterday",
    week: "this week 7 days",
    month: "this month 30 days",
  }[period] || "this week";
  const query = `site:shopee.com.my ${category} viral Malaysia Shopee ${periodWords}`;
  const html = await fetchText(`https://duckduckgo.com/html/?q=${encodeURIComponent(query)}`);
  const results = [];
  const itemRegex = /<a rel="nofollow" class="result__a" href="([^"]+)">([\s\S]*?)<\/a>[\s\S]*?<a class="result__snippet"[\s\S]*?>([\s\S]*?)<\/a>/g;
  for (const match of html.matchAll(itemRegex)) {
    const url = decodeDuckUrl(match[1].replace(/&amp;/g, "&"));
    if (!url.includes("shopee.com.my")) continue;
    const title = match[2].replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim();
    const snippet = match[3].replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim();
    results.push({ title, url, snippet });
    if (results.length >= 12) break;
  }
  return { query, results };
}

async function searchImages(query, productUrl) {
  const imageQuery = `${query} ${productUrl || ""} Shopee Malaysia`;
  const html = await fetchText(`https://duckduckgo.com/?q=${encodeURIComponent(imageQuery)}&iax=images&ia=images`);
  const vqd = (html.match(/vqd=["']([^"']+)/) || [])[1];
  if (!vqd) return [];
  const imageJson = await fetchText(`https://duckduckgo.com/i.js?l=my-en&o=json&q=${encodeURIComponent(imageQuery)}&vqd=${encodeURIComponent(vqd)}&f=,,,&p=1`, {
    referer: "https://duckduckgo.com/",
  });
  const parsed = JSON.parse(imageJson);
  return (parsed.results || [])
    .filter((item) => item.image && item.image.includes("img.susercontent.com"))
    .slice(0, 6)
    .map((item) => ({
      title: item.title,
      image: item.image,
      listing: item.url,
      width: item.width,
      height: item.height,
    }));
}

async function downloadImages(images, productSlug) {
  const assetDir = path.join(generatedDir, "assets", "product");
  fs.mkdirSync(assetDir, { recursive: true });
  const saved = [];
  let index = 1;
  for (const image of images.slice(0, 4)) {
    try {
      const response = await fetch(image.image, {
        headers: {
          "user-agent": "Mozilla/5.0",
          referer: "https://shopee.com.my/",
        },
      });
      if (!response.ok) continue;
      const contentType = response.headers.get("content-type") || "";
      const ext = contentType.includes("png") ? "png" : "jpg";
      const file = `${productSlug}-${String(index).padStart(2, "0")}.${ext}`;
      const buffer = Buffer.from(await response.arrayBuffer());
      fs.writeFileSync(path.join(assetDir, file), buffer);
      saved.push({ ...image, file: `assets/product/${file}` });
      index += 1;
    } catch {
      // Skip individual image failures.
    }
  }
  fs.writeFileSync(path.join(assetDir, "sources.json"), JSON.stringify(saved, null, 2));
  return saved;
}

function categoryCopy(category) {
  const lower = String(category || "").toLowerCase();
  if (lower.includes("case") || lower.includes("phone") || lower.includes("iphone") || lower.includes("gadget")) {
    return {
      eyebrow: "Aksesori harian",
      headline: "Pilihan yang mudah dibeli dan senang digunakan",
      benefits: ["Semak model atau variasi sebelum beli.", "Lihat gambar review untuk rupa sebenar.", "Pilih warna dan gaya yang sesuai dengan penggunaan harian."],
      faq: "Untuk produk aksesori, pastikan model, saiz dan variasi yang dipilih memang tepat.",
    };
  }
  if (lower.includes("home") || lower.includes("rumah") || lower.includes("organizer")) {
    return {
      eyebrow: "Untuk rumah",
      headline: "Barang kecil yang boleh bantu susun ruang harian",
      benefits: ["Sesuai untuk ruang kecil atau kegunaan harian.", "Semak saiz sebenar sebelum beli.", "Pilih warna dan bahan yang sesuai dengan ruang anda."],
      faq: "Untuk produk rumah, semak ukuran dan bahan dalam listing sebelum checkout.",
    };
  }
  return {
    eyebrow: "Produk pilihan",
    headline: "Semak pilihan, harga dan review sebelum beli",
    benefits: ["Sesuai untuk pembelian Shopee yang ringkas.", "Semak harga semasa dan kos penghantaran.", "Pilih penjual dengan rating yang anda selesa."],
    faq: "Baca penerangan penjual, variasi produk dan gambar review sebelum checkout.",
  };
}

function renderSite({ title, category, productUrl, affiliateUrl, images }) {
  const copy = categoryCopy(category);
  const ctaHref = affiliateUrl ? safeText(affiliateUrl) : "#";
  const safeTitle = safeText(title || "Produk Shopee Pilihan");
  const safeCategory = safeText(category || "Produk");
  const slides = images.length
    ? images.map((image, index) => `
              <figure class="slide${index === 0 ? " is-active" : ""}">
                <img src="${safeText(image.file)}" alt="${safeTitle}">
              </figure>`).join("")
    : `
              <figure class="slide is-active">
                <div class="placeholder">Gambar produk akan dipaparkan selepas carian imej berjaya.</div>
              </figure>`;
  const dots = images.length
    ? images.map((_, index) => `<button type="button" class="${index === 0 ? "is-active" : ""}" data-dot="${index}" aria-label="Gambar ${index + 1}"></button>`).join("")
    : `<button type="button" class="is-active" data-dot="0" aria-label="Gambar 1"></button>`;

  return `<!doctype html>
<html lang="ms">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${safeTitle}</title>
    <meta name="description" content="${safeTitle} - semak pilihan, harga dan review di Shopee.">
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <header class="site-header">
      <a class="brand" href="#top"><span class="brand-mark">AP</span><span>Affiliate Pick</span></a>
      <nav><a href="#produk">Produk</a><a href="#komen">Komen</a><a href="#faq">FAQ</a></nav>
    </header>
    <main id="top">
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">${safeText(copy.eyebrow)}</p>
          <h1>${safeTitle}</h1>
          <p class="lead">Pilihan ${safeCategory} untuk anda semak terus di Shopee. Pastikan variasi, harga, penghantaran dan <em>review</em> sesuai sebelum beli.</p>
          <div class="hero-actions">
            <a class="button primary" data-affiliate-link href="${ctaHref}" rel="nofollow sponsored noopener" target="_blank">Lihat di Shopee</a>
            <a class="button secondary" href="#produk">Semak dahulu</a>
          </div>
        </div>
        <section class="product-gallery">
          <div class="slider" data-slider>
            <div class="slides">${slides}
            </div>
            <button class="slider-button prev" type="button" data-prev aria-label="Gambar sebelum">‹</button>
            <button class="slider-button next" type="button" data-next aria-label="Gambar seterusnya">›</button>
            <div class="slider-dots">${dots}</div>
          </div>
        </section>
      </section>
      <section id="produk" class="signal-strip">
        ${copy.benefits.map((benefit) => `<div><strong>${safeText(benefit.split(" ")[0] || "Semak")}</strong><span>${safeText(benefit)}</span></div>`).join("")}
      </section>
      <section class="section two-column">
        <div><p class="eyebrow">Kenapa semak</p><h2>${safeText(copy.headline)}</h2></div>
        <div class="copy-stack">
          <p>Halaman ini dibuat untuk bantu anda lihat produk dengan cepat sebelum pergi ke Shopee.</p>
          <p>Tiada tuntutan berlebihan, tiada diskaun palsu, dan tiada testimoni rekaan.</p>
          <a class="text-link" data-affiliate-link href="${ctaHref}" rel="nofollow sponsored noopener" target="_blank">Buka Shopee</a>
        </div>
      </section>
      <section id="komen" class="section reviews">
        <div class="section-heading"><p class="eyebrow">Komen pembeli</p><h2>Apa yang patut diperhatikan</h2></div>
        <div class="review-grid">
          <article><div class="stars">★★★★★</div><p>Lihat gambar <em>review</em> untuk bandingkan rupa sebenar.</p></article>
          <article><div class="stars">★★★★★</div><p>Semak komen tentang kualiti, saiz dan penghantaran.</p></article>
          <article><div class="stars">★★★★★</div><p>Pilih variasi yang betul sebelum <em>checkout</em>.</p></article>
        </div>
      </section>
      <section id="faq" class="section faq">
        <div class="section-heading"><p class="eyebrow">Sebelum checkout</p><h2>Semak ringkas</h2></div>
        <details open><summary>Apa perlu saya semak?</summary><p>${safeText(copy.faq)}</p></details>
        <details><summary>Adakah link affiliate sudah dipasang?</summary><p>${affiliateUrl ? "Ya, butang CTA menggunakan affiliate link yang dimasukkan." : "Belum. Butang CTA dikosongkan untuk preview dan boleh diisi kemudian."}</p></details>
      </section>
    </main>
    <footer><p>Affiliate disclosure: halaman ini mungkin menerima komisen kecil daripada pembelian melalui pautan Shopee, tanpa kos tambahan kepada anda.</p></footer>
    <script>
      const AFFILIATE_URL = ${JSON.stringify(affiliateUrl || "")};
      document.querySelectorAll("[data-affiliate-link]").forEach((link) => {
        if (AFFILIATE_URL.trim()) { link.href = AFFILIATE_URL; return; }
        link.href = "#"; link.setAttribute("aria-disabled", "true"); link.addEventListener("click", (event) => event.preventDefault());
      });
      const slides = Array.from(document.querySelectorAll(".slide"));
      const dots = Array.from(document.querySelectorAll("[data-dot]"));
      let activeSlide = 0; let autoTimer;
      function showSlide(nextIndex, direction = "next") {
        const current = activeSlide; activeSlide = (nextIndex + slides.length) % slides.length;
        slides.forEach((slide, index) => {
          slide.classList.remove("is-active", "from-right", "from-left", "to-left", "to-right");
          if (index === current && index !== activeSlide) slide.classList.add(direction === "next" ? "to-left" : "to-right");
          if (index === activeSlide) slide.classList.add("is-active", direction === "next" ? "from-right" : "from-left");
        });
        dots.forEach((dot, index) => dot.classList.toggle("is-active", index === activeSlide));
      }
      function restartAutoSlide() { clearInterval(autoTimer); autoTimer = setInterval(() => showSlide(activeSlide + 1, "next"), 4200); }
      document.querySelector("[data-prev]").addEventListener("click", () => { showSlide(activeSlide - 1, "prev"); restartAutoSlide(); });
      document.querySelector("[data-next]").addEventListener("click", () => { showSlide(activeSlide + 1, "next"); restartAutoSlide(); });
      dots.forEach((dot) => dot.addEventListener("click", () => { const nextIndex = Number(dot.dataset.dot); showSlide(nextIndex, nextIndex > activeSlide ? "next" : "prev"); restartAutoSlide(); }));
      restartAutoSlide();
    </script>
  </body>
</html>`;
}

function renderCss() {
  return `:root{color-scheme:light;--ink:#191919;--muted:#5f615b;--paper:#f7f7f5;--surface:#fff;--line:#deded8;--primary:#1d4ed8;--primary-dark:#17368f;--accent:#334155;--shadow:0 18px 42px rgba(20,28,42,.14)}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55;overflow-x:hidden}a{color:inherit}em{font-style:italic}.site-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:14px clamp(18px,4vw,54px);background:rgba(247,247,245,.92);border-bottom:1px solid var(--line);backdrop-filter:blur(14px)}.brand,nav{display:flex;align-items:center;gap:12px}.brand{font-weight:800;text-decoration:none}.brand-mark{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;background:var(--ink);color:var(--paper);font-size:.8rem;letter-spacing:0}nav a{color:var(--muted);font-size:.95rem;font-weight:700;text-decoration:none}.hero{display:grid;grid-template-columns:minmax(0,.9fr) minmax(320px,1.1fr);align-items:center;gap:clamp(28px,5vw,72px);min-height:calc(100vh - 64px);padding:clamp(34px,7vw,92px) clamp(18px,5vw,74px) clamp(28px,5vw,64px)}.hero>*{min-width:0}.hero-copy{min-width:0;max-width:680px}.eyebrow{margin:0 0 12px;color:var(--accent);font-size:.78rem;font-weight:900;letter-spacing:.12em;text-transform:uppercase}h1,h2,h3,p,summary,li{overflow-wrap:anywhere}h1{margin:0;max-width:12ch;font-size:clamp(3rem,8.2vw,6.2rem);line-height:.96;letter-spacing:0}h2{margin:0;font-size:clamp(2rem,4.5vw,4rem);line-height:1;letter-spacing:0}h3{margin:18px 0 8px;font-size:1.18rem}.lead{max-width:58ch;margin:24px 0 0;color:var(--muted);font-size:clamp(1.08rem,2vw,1.32rem)}.hero-actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:30px}.button{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:13px 18px;border:1px solid transparent;border-radius:8px;font-weight:900;text-decoration:none}.button.primary{background:var(--primary);color:white;box-shadow:0 10px 22px rgba(29,78,216,.25)}.button.primary:hover{background:var(--primary-dark)}.button.secondary{background:transparent;border-color:var(--line);color:var(--ink)}.product-gallery{width:100%;max-width:100%;min-width:0}.slider{position:relative;overflow:hidden;width:100%;max-width:100%;border:1px solid var(--line);border-radius:8px;background:var(--surface);box-shadow:var(--shadow)}.slides{position:relative;aspect-ratio:1/1;overflow:hidden}.slide{position:absolute;inset:0;display:grid;place-items:center;margin:0;opacity:0;transform:translateX(100%);transition:opacity 420ms ease,transform 520ms ease}.slide img{display:block;width:100%;height:100%;object-fit:contain;background:white}.slide.is-active{z-index:2;opacity:1;transform:translateX(0)}.slide.from-right{animation:fromRight 520ms ease both}.slide.from-left{animation:fromLeft 520ms ease both}.slide.to-left{z-index:1;opacity:1;animation:toLeft 520ms ease both}.slide.to-right{z-index:1;opacity:1;animation:toRight 520ms ease both}.placeholder{padding:32px;color:var(--muted);text-align:center}.slider-button{position:absolute;top:50%;z-index:4;display:grid;place-items:center;width:42px;height:42px;border:1px solid rgba(0,0,0,.08);border-radius:999px;background:rgba(255,255,255,.92);cursor:pointer;font-size:2rem;line-height:1;transform:translateY(-50%)}.slider-button.prev{left:14px}.slider-button.next{right:14px}.slider-dots{position:absolute;right:0;bottom:12px;left:0;z-index:4;display:flex;justify-content:center;gap:8px}.slider-dots button{width:9px;height:9px;padding:0;border:0;border-radius:50%;background:rgba(25,25,25,.25);cursor:pointer}.slider-dots button.is-active{background:var(--primary)}.signal-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:0 clamp(18px,5vw,74px);overflow:hidden;border:1px solid var(--line);border-radius:8px;background:var(--line)}.signal-strip div{min-height:126px;padding:22px;background:var(--surface)}.signal-strip strong,.signal-strip span{display:block}.signal-strip strong{margin-bottom:8px;font-size:1.05rem}.signal-strip span{color:var(--muted)}.section{padding:clamp(58px,9vw,112px) clamp(18px,5vw,74px)}.two-column{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:clamp(24px,5vw,68px)}.copy-stack p{margin:0 0 18px;color:var(--muted);font-size:1.08rem}.text-link{display:inline-flex;margin-top:4px;color:var(--primary-dark);font-weight:900;text-decoration-thickness:2px;text-underline-offset:5px}.section-heading{max-width:760px;margin-bottom:28px}.review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.review-grid article{min-height:208px;padding:24px;border:1px solid var(--line);border-radius:8px;background:var(--surface)}.review-grid p{margin:0;color:var(--muted)}.stars{margin-bottom:14px;color:#f0a51a;letter-spacing:.08em}.faq{max-width:980px}details{border-top:1px solid var(--line);background:transparent}details:last-child{border-bottom:1px solid var(--line)}summary{cursor:pointer;padding:20px 0;font-weight:900}details p{max-width:75ch;margin:0 0 20px;color:var(--muted)}footer{padding:24px clamp(18px,5vw,74px) 42px;color:var(--muted);font-size:.76rem}@keyframes fromRight{from{opacity:1;transform:translateX(100%)}to{opacity:1;transform:translateX(0)}}@keyframes fromLeft{from{opacity:1;transform:translateX(-100%)}to{opacity:1;transform:translateX(0)}}@keyframes toLeft{from{opacity:1;transform:translateX(0)}to{opacity:1;transform:translateX(-100%)}}@keyframes toRight{from{opacity:1;transform:translateX(0)}to{opacity:1;transform:translateX(100%)}}@media(max-width:860px){.site-header{align-items:flex-start;flex-direction:column;gap:10px}.hero{grid-template-columns:1fr;min-height:auto;width:100%;padding-right:26px;padding-left:26px;overflow:hidden}.hero-copy,.lead,.product-gallery{width:100%;max-width:28ch}.product-gallery{justify-self:center;order:-1}h1{max-width:10ch}.signal-strip,.review-grid,.two-column{grid-template-columns:1fr}}@media(max-width:520px){nav{width:100%;flex-wrap:wrap;justify-content:flex-start;gap:10px 18px}.hero-actions,.button{width:100%}h1{font-size:clamp(2.5rem,16vw,3.8rem)}h2{font-size:clamp(1.85rem,11vw,3rem)}.slider-button{width:36px;height:36px}}`;
}

function emptyDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

async function generateSite(payload) {
  const productUrl = String(payload.productUrl || payload.selectedUrl || "").trim();
  const affiliateUrl = String(payload.affiliateUrl || "").trim();
  const category = String(payload.category || "produk").trim();
  const title = String(payload.title || payload.selectedTitle || category || "Produk Shopee Pilihan").trim();
  const slug = safeFileName(title);
  emptyDir(generatedDir);
  const imageResults = await searchImages(title || category, productUrl);
  const images = await downloadImages(imageResults, slug);
  fs.writeFileSync(path.join(generatedDir, "index.html"), renderSite({ title, category, productUrl, affiliateUrl, images }));
  fs.writeFileSync(path.join(generatedDir, "styles.css"), renderCss());
  fs.writeFileSync(path.join(generatedDir, "generation.json"), JSON.stringify({ title, category, productUrl, affiliateUrl: affiliateUrl ? "[set]" : "", imageCount: images.length, generatedAt: new Date().toISOString() }, null, 2));
  return { previewUrl: "/preview/", imageCount: images.length, generatedDir };
}

function getStatus() {
  let site = null;
  if (fs.existsSync(siteConfigPath)) {
    site = JSON.parse(fs.readFileSync(siteConfigPath, "utf8").replace(/^\uFEFF/, ""));
  }
  return {
    site,
    hasGeneratedSite: fs.existsSync(path.join(generatedDir, "index.html")),
    hasNetlifyToken: Boolean(process.env.NETLIFY_AUTH_TOKEN),
  };
}

function publishSite() {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(path.join(generatedDir, "index.html"))) {
      reject(new Error("Generate a site before publishing."));
      return;
    }
    const site = getStatus().site;
    if (!site || !site.site_id) {
      reject(new Error("Missing scripts/netlify-site.local.json site_id."));
      return;
    }
    if (!process.env.NETLIFY_AUTH_TOKEN) {
      reject(new Error("Missing NETLIFY_AUTH_TOKEN in the local server environment."));
      return;
    }
    const args = ["--yes", "netlify-cli", "deploy", "--prod", "--json", "--dir", generatedDir, "--site", site.site_id];
    const child = spawn("npx", args, { cwd: workspace, env: process.env, shell: process.platform === "win32" });
    let output = "";
    let errorOutput = "";
    child.stdout.on("data", (data) => { output += data.toString(); });
    child.stderr.on("data", (data) => { errorOutput += data.toString(); });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(errorOutput || output || `Netlify deploy failed with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(output));
      } catch {
        resolve({ output });
      }
    });
  });
}

function serveStatic(req, res, baseDir, prefix = "") {
  const url = new URL(req.url, "http://localhost");
  let relative = decodeURIComponent(url.pathname.slice(prefix.length));
  if (!relative || relative.endsWith("/")) relative += "index.html";
  const filePath = path.normalize(path.join(baseDir, relative));
  if (!filePath.startsWith(baseDir)) {
    send(res, 403, "Forbidden", "text/plain; charset=utf-8");
    return true;
  }
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) return false;
  res.writeHead(200, { "Content-Type": mime[path.extname(filePath).toLowerCase()] || "application/octet-stream" });
  fs.createReadStream(filePath).pipe(res);
  return true;
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    if (req.method === "GET" && url.pathname === "/api/status") {
      send(res, 200, getStatus());
      return;
    }
    if (req.method === "GET" && url.pathname === "/api/search") {
      const result = await searchWeb(url.searchParams.get("category") || "", url.searchParams.get("period") || "week");
      send(res, 200, result);
      return;
    }
    if (req.method === "POST" && url.pathname === "/api/generate") {
      const result = await generateSite(await readJson(req));
      send(res, 200, result);
      return;
    }
    if (req.method === "POST" && url.pathname === "/api/publish") {
      const result = await publishSite();
      send(res, 200, result);
      return;
    }
    if (url.pathname.startsWith("/preview/")) {
      if (serveStatic(req, res, generatedDir, "/preview/")) return;
    }
    if (serveStatic(req, res, publicDir)) return;
    send(res, 404, "Not found", "text/plain; charset=utf-8");
  } catch (error) {
    send(res, 500, { error: error.message });
  }
});

const port = Number(process.env.PORT || 8787);
server.listen(port, () => {
  console.log(`Affiliate Builder UI: http://localhost:${port}`);
});
