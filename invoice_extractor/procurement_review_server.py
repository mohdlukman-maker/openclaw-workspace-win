import argparse
import csv
import io
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from procurement_query import answer_question


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "procurement_index.sqlite"


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Procurement Review</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7f8;
      --panel: #ffffff;
      --line: #d7dee2;
      --text: #1d2529;
      --muted: #657178;
      --accent: #166b5d;
      --warn: #9a5b00;
      --bad: #9b1c31;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.4 "Segoe UI", Arial, sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    .header-actions { display: flex; align-items: center; gap: 12px; min-width: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(320px, 430px) 1fr;
      min-height: calc(100vh - 56px);
    }
    aside {
      border-right: 1px solid var(--line);
      background: var(--panel);
      overflow: auto;
      max-height: calc(100vh - 56px);
    }
    section {
      padding: 16px;
      overflow: auto;
      max-height: calc(100vh - 56px);
    }
    .toolbar {
      display: flex;
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      background: var(--panel);
      z-index: 1;
    }
    .section-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin: 4px 0 10px;
    }
    .section-title h2 { margin: 0; font-size: 16px; }
    .link-button {
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--text);
      background: #fff;
      text-decoration: none;
    }
    input, select, button, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    input, select, textarea { padding: 7px 8px; }
    button {
      padding: 7px 10px;
      cursor: pointer;
      background: #fff;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button.danger { color: var(--bad); }
    button:disabled { opacity: .5; cursor: default; }
    .search { width: 100%; }
    .doc {
      width: 100%;
      text-align: left;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      padding: 10px 12px;
      background: var(--panel);
    }
    .doc:hover, .doc.active { background: #eef4f2; }
    .doc-title { font-weight: 650; overflow-wrap: anywhere; }
    .doc-meta, .muted { color: var(--muted); font-size: 12px; }
    .stats {
      display: grid;
      grid-template-columns: repeat(5, minmax(100px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }
    .stat strong { display: block; font-size: 20px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 14px;
      overflow: hidden;
    }
    .panel h2 {
      font-size: 15px;
      margin: 0;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfc;
    }
    .analytics-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(260px, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }
    .analytics-grid .panel { margin-bottom: 0; }
    .ask-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      padding: 12px;
    }
    .answer {
      padding: 0 12px 12px;
    }
    .suggestions {
      border-top: 1px solid var(--line);
      max-height: 220px;
      overflow: auto;
    }
    .suggestion {
      width: 100%;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      text-align: left;
      padding: 9px 12px;
      background: #fff;
    }
    .suggestion:hover { background: #eef4f2; }
    .grid {
      display: grid;
      grid-template-columns: 160px 1fr 160px 1fr;
      gap: 8px 12px;
      padding: 12px;
    }
    .label { color: var(--muted); }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }
    th { background: #fbfcfc; font-weight: 650; }
    td input, td select { width: 100%; min-width: 0; }
    .desc { width: 34%; }
    .narrow { width: 95px; }
    .amount { text-align: right; }
    .status {
      display: inline-flex;
      padding: 2px 7px;
      border-radius: 999px;
      background: #edf1f3;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .status.approved { background: #e6f5ef; color: var(--accent); }
    .status.rejected { background: #f8e8ec; color: var(--bad); }
    .status.issue { background: #fff4df; color: var(--warn); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px; border-top: 1px solid var(--line); }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      aside, section { max-height: none; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .analytics-grid { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Procurement Review</h1>
    <div class="header-actions">
      <a class="link-button" href="/api/export?name=line_items">Export Items CSV</a>
      <a class="link-button" href="/api/export?name=purchase_orders">Export P.O CSV</a>
      <div id="dbPath" class="muted"></div>
    </div>
  </header>
  <main>
    <aside>
      <div class="toolbar">
        <input id="search" class="search" placeholder="Search file, supplier, PO">
        <select id="statusFilter">
          <option value="">All</option>
          <option value="needs_review">Needs review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>
      <div id="documents"></div>
    </aside>
    <section>
      <div id="stats" class="stats"></div>
      <div class="panel">
        <h2>Item Lookup</h2>
        <div class="ask-row">
          <input id="itemSearch" placeholder="Start typing an item name">
          <button onclick="clearItemLookup()">Clear</button>
        </div>
        <div id="itemSuggestions" class="suggestions"></div>
        <div id="itemDetail" class="answer muted">Select an item to see unit prices, total quantity, and top 3 contacts.</div>
      </div>
      <div class="section-title">
        <h2>Analytics</h2>
        <button onclick="loadAnalytics()">Refresh</button>
      </div>
      <div id="analytics" class="analytics-grid"></div>
      <div id="detail" class="muted">Select a document to review.</div>
    </section>
  </main>
  <script>
    let documents = [];
    let activeId = null;

    async function api(path, options) {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    function money(value) {
      if (value === null || value === undefined || value === "") return "";
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(2) : value;
    }

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[ch]);
    }

    function qty(value) {
      if (value === null || value === undefined || value === "") return "";
      const number = Number(value);
      return Number.isFinite(number) ? number.toLocaleString(undefined, {maximumFractionDigits: 2}) : value;
    }

    function tablePanel(title, rows, columns) {
      return `
        <div class="panel">
          <h2>${esc(title)}</h2>
          <table>
            <thead><tr>${columns.map(col => `<th>${esc(col.label)}</th>`).join("")}</tr></thead>
            <tbody>
              ${rows.map(row => `
                <tr>
                  ${columns.map(col => {
                    const value = col.money ? money(row[col.key]) : col.qty ? qty(row[col.key]) : row[col.key];
                    return `<td class="${col.money || col.qty ? "amount" : ""}">${esc(value)}</td>`;
                  }).join("")}
                </tr>
              `).join("") || `<tr><td colspan="${columns.length}" class="muted">No data.</td></tr>`}
            </tbody>
          </table>
        </div>
      `;
    }

    async function loadSummary() {
      const summary = await api("/api/summary");
      document.getElementById("dbPath").textContent = summary.db_path;
      document.getElementById("stats").innerHTML = [
        ["Documents", summary.counts.source_documents],
        ["P.O", summary.counts.purchase_orders],
        ["MR", summary.counts.material_requisitions],
        ["Items", summary.counts.line_items],
        ["Issues", summary.counts.review_issues],
      ].map(([label, value]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`).join("");
    }

    async function loadDocuments() {
      documents = await api("/api/documents");
      renderDocuments();
    }

    async function loadAnalytics() {
      const analytics = await api("/api/analytics");
      document.getElementById("analytics").innerHTML = [
        tablePanel("Most Bought Items", analytics.top_items_by_quantity, [
          {label: "Item", key: "description"},
          {label: "Qty", key: "quantity", qty: true},
          {label: "Spend", key: "spend", money: true},
        ]),
        tablePanel("Highest Unit Prices", analytics.most_expensive_items, [
          {label: "Item", key: "description"},
          {label: "Unit Price", key: "unit_price", money: true},
          {label: "Source", key: "source"},
        ]),
        tablePanel("Supplier Spend", analytics.supplier_spend, [
          {label: "Supplier", key: "supplier"},
          {label: "P.O", key: "po_count", qty: true},
          {label: "Spend", key: "spend", money: true},
        ]),
        tablePanel("Monthly Spend", analytics.monthly_spend, [
          {label: "Month", key: "month_code"},
          {label: "P.O", key: "po_count", qty: true},
          {label: "Spend", key: "spend", money: true},
        ]),
        tablePanel("Top Contacts", analytics.contact_activity, [
          {label: "Contact", key: "contact"},
          {label: "P.O", key: "po_count", qty: true},
          {label: "Spend", key: "spend", money: true},
        ]),
        tablePanel("Review Issues", analytics.review_issue_summary, [
          {label: "Issue", key: "issue_type"},
          {label: "Open", key: "open_count", qty: true},
          {label: "Total", key: "total_count", qty: true},
        ]),
      ].join("");
    }

    let itemSearchTimer = null;

    async function searchItems() {
      const query = document.getElementById("itemSearch").value.trim();
      const suggestions = document.getElementById("itemSuggestions");
      if (!query) {
        suggestions.innerHTML = "";
        return;
      }
      const rows = await api(`/api/items?q=${encodeURIComponent(query)}`);
      suggestions.innerHTML = rows.map(item => `
        <button class="suggestion" onclick="loadItemDetail(${item.id})">
          <div class="doc-title">${esc(item.canonical_name)}</div>
          <div class="doc-meta">Qty ${qty(item.quantity)} &middot; Spend ${money(item.spend)} &middot; ${item.line_count} lines</div>
        </button>
      `).join("") || `<div class="answer muted">No matching item.</div>`;
    }

    async function loadItemDetail(itemId) {
      const detail = await api(`/api/item-detail?id=${itemId}`);
      document.getElementById("itemSearch").value = detail.item.canonical_name;
      document.getElementById("itemSuggestions").innerHTML = "";
      document.getElementById("itemDetail").innerHTML = `
        <div class="stats">
          <div class="stat"><strong>${qty(detail.summary.total_quantity)}</strong><span>Total quantity</span></div>
          <div class="stat"><strong>${money(detail.summary.total_spend)}</strong><span>Total spend</span></div>
          <div class="stat"><strong>${money(detail.summary.avg_unit_price)}</strong><span>Average unit price</span></div>
          <div class="stat"><strong>${money(detail.summary.min_unit_price)}</strong><span>Lowest unit price</span></div>
          <div class="stat"><strong>${money(detail.summary.max_unit_price)}</strong><span>Highest unit price</span></div>
        </div>
        ${tablePanel("Top 3 Contacts", detail.top_contacts, [
          {label: "Contact", key: "contact"},
          {label: "Qty", key: "quantity", qty: true},
          {label: "P.O", key: "po_count", qty: true},
          {label: "Spend", key: "spend", money: true},
        ])}
        ${tablePanel("Unit Price Records", detail.price_records, [
          {label: "Date", key: "po_date"},
          {label: "Supplier", key: "supplier"},
          {label: "Qty", key: "quantity_raw"},
          {label: "Unit Price", key: "unit_price", money: true},
          {label: "Amount", key: "amount", money: true},
          {label: "Source", key: "source"},
        ])}
      `;
    }

    function clearItemLookup() {
      document.getElementById("itemSearch").value = "";
      document.getElementById("itemSuggestions").innerHTML = "";
      document.getElementById("itemDetail").innerHTML = "Select an item to see unit prices, total quantity, and top 3 contacts.";
    }

    document.getElementById("itemSearch").addEventListener("input", () => {
      clearTimeout(itemSearchTimer);
      itemSearchTimer = setTimeout(searchItems, 150);
    });

    function renderDocuments() {
      const search = document.getElementById("search").value.toLowerCase();
      const status = document.getElementById("statusFilter").value;
      const filtered = documents.filter(doc => {
        const haystack = `${doc.file_name} ${doc.supplier_name_from_filename} ${doc.po_number_from_filename}`.toLowerCase();
        return (!status || doc.review_status === status) && (!search || haystack.includes(search));
      });
      document.getElementById("documents").innerHTML = filtered.map(doc => `
        <button class="doc ${doc.id === activeId ? "active" : ""}" onclick="loadDetail(${doc.id})">
          <div class="doc-title">${esc(doc.file_name)}</div>
          <div class="doc-meta">${esc(doc.supplier_name_from_filename)} &middot; PO ${esc(doc.po_number_from_filename)}</div>
          <div class="doc-meta">
            <span class="status ${esc(doc.review_status)}">${esc(doc.review_status)}</span>
            <span class="status ${doc.issue_count ? "issue" : ""}">${doc.issue_count} issues</span>
            <span>${doc.item_count} items</span>
          </div>
        </button>
      `).join("");
    }

    async function setDocumentStatus(status) {
      await api("/api/document-status", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: activeId, status})
      });
      await loadDocuments();
      await loadSummary();
      await loadDetail(activeId);
    }

    async function updateIssue(id, resolved) {
      const notes = document.getElementById(`issue-notes-${id}`).value;
      await api("/api/issue", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id, resolved, notes})
      });
      await loadSummary();
      await loadDetail(activeId);
    }

    async function updateLineItem(id) {
      const data = {};
      for (const field of ["raw_description", "quantity_raw", "quantity_value", "quantity_unit", "unit_price", "amount", "review_status"]) {
        data[field] = document.getElementById(`li-${id}-${field}`).value;
      }
      data.id = id;
      await api("/api/line-item", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
      });
      await loadSummary();
      await loadDetail(activeId);
    }

    async function loadDetail(id) {
      activeId = id;
      renderDocuments();
      const detail = await api(`/api/document?id=${id}`);
      const doc = detail.document;
      const po = detail.purchase_order || {};
      const mr = detail.material_requisition || {};
      document.getElementById("detail").innerHTML = `
        <div class="panel">
          <h2>${esc(doc.file_name)}</h2>
          <div class="grid">
            <div class="label">Supplier</div><div>${esc(doc.supplier_name_from_filename)}</div>
            <div class="label">Status</div><div><span class="status ${esc(doc.review_status)}">${esc(doc.review_status)}</span></div>
            <div class="label">PO Number</div><div>${esc(po.po_number || doc.po_number_from_filename)}</div>
            <div class="label">PO Reference</div><div>${esc(po.po_reference)}</div>
            <div class="label">PO Date</div><div>${esc(po.po_date)}</div>
            <div class="label">D.O No</div><div>${esc(po.delivery_order_no)}</div>
            <div class="label">MR Reference</div><div>${esc(mr.mr_reference)}</div>
            <div class="label">MR Date</div><div>${esc(mr.date_request)}</div>
            <div class="label">Template</div><div>${esc(doc.template_variant)}</div>
            <div class="label">Source</div><div>${esc(doc.source_path)}</div>
          </div>
          <div class="actions">
            <button class="primary" onclick="setDocumentStatus('approved')">Approve document</button>
            <button onclick="setDocumentStatus('needs_review')">Needs review</button>
            <button class="danger" onclick="setDocumentStatus('rejected')">Reject</button>
          </div>
        </div>
        <div class="panel">
          <h2>Line Items</h2>
          <table>
            <thead>
              <tr>
                <th class="narrow">No.</th>
                <th class="desc">Description</th>
                <th class="narrow">Qty</th>
                <th class="narrow">Unit</th>
                <th class="narrow">Unit Price</th>
                <th class="narrow">Amount</th>
                <th class="narrow">Status</th>
                <th class="narrow"></th>
              </tr>
            </thead>
            <tbody>
              ${detail.line_items.map(item => `
                <tr>
                  <td>${item.row_number}</td>
                  <td><input id="li-${item.id}-raw_description" value="${esc(item.raw_description)}"></td>
                  <td>
                    <input id="li-${item.id}-quantity_raw" value="${esc(item.quantity_raw)}">
                    <input id="li-${item.id}-quantity_value" type="hidden" value="${esc(item.quantity_value)}">
                  </td>
                  <td><input id="li-${item.id}-quantity_unit" value="${esc(item.quantity_unit)}"></td>
                  <td><input id="li-${item.id}-unit_price" value="${esc(money(item.unit_price))}"></td>
                  <td><input id="li-${item.id}-amount" value="${esc(money(item.amount))}"></td>
                  <td>
                    <select id="li-${item.id}-review_status">
                      ${["needs_review","approved","rejected"].map(status => `<option value="${status}" ${item.review_status === status ? "selected" : ""}>${status}</option>`).join("")}
                    </select>
                  </td>
                  <td><button onclick="updateLineItem(${item.id})">Save</button></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
        <div class="panel">
          <h2>Review Issues</h2>
          <table>
            <thead><tr><th>Field</th><th>Issue</th><th>Severity</th><th>Notes</th><th class="narrow">Resolved</th></tr></thead>
            <tbody>
              ${detail.review_issues.map(issue => `
                <tr>
                  <td>${esc(issue.field_name)}</td>
                  <td>${esc(issue.issue_type)}</td>
                  <td><span class="status issue">${esc(issue.severity)}</span></td>
                  <td><textarea id="issue-notes-${issue.id}" rows="2">${esc(issue.notes)}</textarea></td>
                  <td>
                    <button onclick="updateIssue(${issue.id}, ${issue.resolved ? 0 : 1})">${issue.resolved ? "Reopen" : "Resolve"}</button>
                  </td>
                </tr>
              `).join("") || `<tr><td colspan="5" class="muted">No issues.</td></tr>`}
            </tbody>
          </table>
        </div>
      `;
    }

    document.getElementById("search").addEventListener("input", renderDocuments);
    document.getElementById("statusFilter").addEventListener("change", renderDocuments);
    loadSummary().then(loadDocuments).then(loadAnalytics);
  </script>
</body>
</html>
"""


def dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, object]]:
    return [dict(row) for row in cursor.fetchall()]


class ReviewServer(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB_PATH

    def log_message(self, format: str, *args: object) -> None:
        return

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self, file_name: str, rows: list[dict[str, object]]) -> None:
        output = io.StringIO()
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self.send_html()
            elif parsed.path == "/api/summary":
                self.send_json(self.summary())
            elif parsed.path == "/api/documents":
                self.send_json(self.documents())
            elif parsed.path == "/api/document":
                document_id = int(parse_qs(parsed.query).get("id", ["0"])[0])
                self.send_json(self.document_detail(document_id))
            elif parsed.path == "/api/analytics":
                self.send_json(self.analytics())
            elif parsed.path == "/api/items":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self.send_json(self.item_suggestions(query))
            elif parsed.path == "/api/item-detail":
                item_id = int(parse_qs(parsed.query).get("id", ["0"])[0])
                self.send_json(self.item_detail(item_id))
            elif parsed.path == "/api/export":
                name = parse_qs(parsed.query).get("name", ["line_items"])[0]
                file_name, rows = self.export_rows(name)
                self.send_csv(file_name, rows)
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self.read_json()
        try:
            if parsed.path == "/api/document-status":
                self.update_document_status(payload)
            elif parsed.path == "/api/line-item":
                self.update_line_item(payload)
            elif parsed.path == "/api/issue":
                self.update_issue(payload)
            elif parsed.path == "/api/ask":
                self.send_json(self.ask(payload))
                return
            else:
                self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"ok": True})
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def summary(self) -> dict[str, object]:
        with self.connect() as connection:
            counts = {}
            for table in [
                "source_documents",
                "purchase_orders",
                "material_requisitions",
                "line_items",
                "suppliers",
                "contacts",
                "review_issues",
            ]:
                counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts["open_review_issues"] = connection.execute(
                "SELECT COUNT(*) FROM review_issues WHERE resolved = 0"
            ).fetchone()[0]
        return {"db_path": str(self.db_path), "counts": counts}

    def documents(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            return dict_rows(
                connection.execute(
                    """
                    SELECT
                        sd.id,
                        sd.file_name,
                        sd.source_path,
                        sd.supplier_name_from_filename,
                        sd.po_number_from_filename,
                        sd.template_variant,
                        sd.review_status,
                        COUNT(DISTINCT li.id) AS item_count,
                        COUNT(DISTINCT CASE WHEN ri.resolved = 0 THEN ri.id END) AS issue_count
                    FROM source_documents sd
                    LEFT JOIN purchase_orders po ON po.source_document_id = sd.id
                    LEFT JOIN line_items li ON li.purchase_order_id = po.id
                    LEFT JOIN review_issues ri ON ri.source_document_id = sd.id
                    GROUP BY sd.id
                    ORDER BY sd.id
                    """
                )
            )

    def document_detail(self, document_id: int) -> dict[str, object]:
        with self.connect() as connection:
            document = connection.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
            if document is None:
                raise ValueError("Document not found")
            purchase_order = connection.execute(
                "SELECT * FROM purchase_orders WHERE source_document_id = ?", (document_id,)
            ).fetchone()
            material_requisition = connection.execute(
                "SELECT * FROM material_requisitions WHERE source_document_id = ?", (document_id,)
            ).fetchone()
            line_items = dict_rows(
                connection.execute(
                    """
                    SELECT li.*
                    FROM line_items li
                    JOIN purchase_orders po ON po.id = li.purchase_order_id
                    WHERE po.source_document_id = ?
                    ORDER BY li.row_number, li.id
                    """,
                    (document_id,),
                )
            )
            issues = dict_rows(
                connection.execute(
                    "SELECT * FROM review_issues WHERE source_document_id = ? ORDER BY resolved, severity DESC, id",
                    (document_id,),
                )
            )
        return {
            "document": dict(document),
            "purchase_order": dict(purchase_order) if purchase_order else None,
            "material_requisition": dict(material_requisition) if material_requisition else None,
            "line_items": line_items,
            "review_issues": issues,
        }

    def analytics(self) -> dict[str, object]:
        with self.connect() as connection:
            top_items_by_quantity = dict_rows(
                connection.execute(
                    """
                    SELECT
                        COALESCE(i.canonical_name, li.raw_description) AS description,
                        SUM(COALESCE(li.quantity_value, 0)) AS quantity,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM line_items li
                    LEFT JOIN items i ON i.id = li.normalized_item_id
                    WHERE li.review_status != 'rejected'
                      AND COALESCE(li.raw_description, '') != ''
                    GROUP BY COALESCE(li.normalized_item_id, LOWER(TRIM(li.raw_description)))
                    ORDER BY quantity DESC, spend DESC
                    LIMIT 10
                    """
                )
            )
            most_expensive_items = dict_rows(
                connection.execute(
                    """
                    SELECT
                        COALESCE(i.canonical_name, li.raw_description) AS description,
                        li.unit_price,
                        sd.file_name AS source
                    FROM line_items li
                    LEFT JOIN items i ON i.id = li.normalized_item_id
                    JOIN purchase_orders po ON po.id = li.purchase_order_id
                    JOIN source_documents sd ON sd.id = po.source_document_id
                    WHERE li.review_status != 'rejected'
                      AND li.unit_price IS NOT NULL
                    ORDER BY li.unit_price DESC, li.amount DESC
                    LIMIT 10
                    """
                )
            )
            supplier_spend = dict_rows(
                connection.execute(
                    """
                    SELECT
                        COALESCE(s.canonical_name, sd.supplier_name_from_filename, 'Unknown') AS supplier,
                        COUNT(DISTINCT po.id) AS po_count,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM purchase_orders po
                    JOIN source_documents sd ON sd.id = po.source_document_id
                    LEFT JOIN suppliers s ON s.id = po.supplier_id
                    LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
                    WHERE po.review_status != 'rejected'
                    GROUP BY supplier
                    ORDER BY spend DESC, po_count DESC
                    LIMIT 10
                    """
                )
            )
            monthly_spend = dict_rows(
                connection.execute(
                    """
                    SELECT
                        sd.month_code,
                        COUNT(DISTINCT po.id) AS po_count,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM source_documents sd
                    JOIN purchase_orders po ON po.source_document_id = sd.id
                    LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
                    WHERE po.review_status != 'rejected'
                    GROUP BY sd.month_code
                    ORDER BY sd.month_code
                    """
                )
            )
            contact_activity = dict_rows(
                connection.execute(
                    """
                    SELECT
                        COALESCE(c.name, 'Unknown') AS contact,
                        COUNT(DISTINCT po.id) AS po_count,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM purchase_orders po
                    LEFT JOIN contacts c ON c.id = po.person_to_contact_id
                    LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
                    WHERE po.review_status != 'rejected'
                    GROUP BY contact
                    ORDER BY po_count DESC, spend DESC
                    LIMIT 10
                    """
                )
            )
            review_issue_summary = dict_rows(
                connection.execute(
                    """
                    SELECT
                        issue_type,
                        SUM(CASE WHEN resolved = 0 THEN 1 ELSE 0 END) AS open_count,
                        COUNT(*) AS total_count
                    FROM review_issues
                    GROUP BY issue_type
                    ORDER BY open_count DESC, total_count DESC
                    """
                )
            )
        return {
            "top_items_by_quantity": top_items_by_quantity,
            "most_expensive_items": most_expensive_items,
            "supplier_spend": supplier_spend,
            "monthly_spend": monthly_spend,
            "contact_activity": contact_activity,
            "review_issue_summary": review_issue_summary,
        }

    def item_suggestions(self, query: str) -> list[dict[str, object]]:
        query = query.strip()
        if not query:
            return []
        with self.connect() as connection:
            return dict_rows(
                connection.execute(
                    """
                    SELECT
                        i.id,
                        i.canonical_name,
                        COUNT(li.id) AS line_count,
                        SUM(COALESCE(li.quantity_value, 0)) AS quantity,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM items i
                    LEFT JOIN line_items li ON li.normalized_item_id = i.id AND li.review_status != 'rejected'
                    WHERE i.canonical_name LIKE ?
                    GROUP BY i.id
                    ORDER BY
                        CASE WHEN i.canonical_name LIKE ? THEN 0 ELSE 1 END,
                        quantity DESC,
                        i.canonical_name
                    LIMIT 50
                    """,
                    (f"%{query}%", f"{query}%"),
                )
            )

    def item_detail(self, item_id: int) -> dict[str, object]:
        with self.connect() as connection:
            item = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if item is None:
                raise ValueError("Item not found")
            summary = connection.execute(
                """
                SELECT
                    SUM(COALESCE(quantity_value, 0)) AS total_quantity,
                    SUM(COALESCE(amount, 0)) AS total_spend,
                    AVG(unit_price) AS avg_unit_price,
                    MIN(unit_price) AS min_unit_price,
                    MAX(unit_price) AS max_unit_price
                FROM line_items
                WHERE normalized_item_id = ?
                  AND review_status != 'rejected'
                """,
                (item_id,),
            ).fetchone()
            top_contacts = dict_rows(
                connection.execute(
                    """
                    SELECT
                        COALESCE(c.name, 'Unknown') AS contact,
                        SUM(COALESCE(li.quantity_value, 0)) AS quantity,
                        COUNT(DISTINCT po.id) AS po_count,
                        SUM(COALESCE(li.amount, 0)) AS spend
                    FROM line_items li
                    JOIN purchase_orders po ON po.id = li.purchase_order_id
                    LEFT JOIN contacts c ON c.id = po.person_to_contact_id
                    WHERE li.normalized_item_id = ?
                      AND li.review_status != 'rejected'
                    GROUP BY contact
                    ORDER BY quantity DESC, spend DESC, po_count DESC
                    LIMIT 3
                    """,
                    (item_id,),
                )
            )
            price_records = dict_rows(
                connection.execute(
                    """
                    SELECT
                        po.po_date,
                        COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                        li.quantity_raw,
                        li.unit_price,
                        li.amount,
                        sd.file_name AS source
                    FROM line_items li
                    JOIN purchase_orders po ON po.id = li.purchase_order_id
                    JOIN source_documents sd ON sd.id = po.source_document_id
                    LEFT JOIN suppliers s ON s.id = po.supplier_id
                    WHERE li.normalized_item_id = ?
                      AND li.review_status != 'rejected'
                    ORDER BY COALESCE(po.po_date, sd.month_code) DESC, po.po_number DESC, li.id DESC
                    LIMIT 20
                    """,
                    (item_id,),
                )
            )
        return {
            "item": dict(item),
            "summary": dict(summary) if summary else {},
            "top_contacts": top_contacts,
            "price_records": price_records,
        }

    def export_rows(self, name: str) -> tuple[str, list[dict[str, object]]]:
        with self.connect() as connection:
            if name == "purchase_orders":
                rows = dict_rows(
                    connection.execute(
                        """
                        SELECT
                            sd.file_name,
                            sd.source_path,
                            po.po_number,
                            po.po_reference,
                            po.po_date,
                            COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                            po.delivery_order_no,
                            po.total_amount,
                            po.review_status
                        FROM purchase_orders po
                        JOIN source_documents sd ON sd.id = po.source_document_id
                        LEFT JOIN suppliers s ON s.id = po.supplier_id
                        ORDER BY sd.month_code, po.po_number, sd.file_name
                        """
                    )
                )
                return "procurement_purchase_orders.csv", rows
            if name != "line_items":
                raise ValueError("Unknown export")
            rows = dict_rows(
                connection.execute(
                    """
                    SELECT
                        sd.file_name,
                        sd.source_path,
                        sd.month_code,
                        po.po_number,
                        po.po_reference,
                        po.po_date,
                        COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                        mr.mr_reference,
                        li.row_number,
                        COALESCE(i.canonical_name, li.raw_description) AS normalized_item,
                        li.raw_description,
                        li.quantity_raw,
                        li.quantity_value,
                        li.quantity_unit,
                        li.unit_price,
                        li.amount,
                        li.review_status
                    FROM line_items li
                    JOIN purchase_orders po ON po.id = li.purchase_order_id
                    JOIN source_documents sd ON sd.id = po.source_document_id
                    LEFT JOIN items i ON i.id = li.normalized_item_id
                    LEFT JOIN material_requisitions mr ON mr.id = li.material_requisition_id
                    LEFT JOIN suppliers s ON s.id = po.supplier_id
                    ORDER BY sd.month_code, po.po_number, li.row_number, li.id
                    """
                )
            )
        return "procurement_line_items.csv", rows

    def ask(self, payload: dict[str, object]) -> dict[str, object]:
        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("Question is required")
        return answer_question(question, self.db_path)

    def update_document_status(self, payload: dict[str, object]) -> None:
        document_id = int(payload["id"])
        status = str(payload["status"])
        if status not in {"needs_review", "approved", "rejected"}:
            raise ValueError("Invalid status")
        with self.connect() as connection:
            connection.execute("UPDATE source_documents SET review_status = ? WHERE id = ?", (status, document_id))
            connection.execute(
                "UPDATE purchase_orders SET review_status = ? WHERE source_document_id = ?",
                (status, document_id),
            )
            connection.execute(
                "UPDATE material_requisitions SET review_status = ? WHERE source_document_id = ?",
                (status, document_id),
            )
            connection.execute(
                """
                UPDATE line_items
                SET review_status = ?
                WHERE purchase_order_id IN (SELECT id FROM purchase_orders WHERE source_document_id = ?)
                """,
                (status, document_id),
            )
            connection.commit()

    def update_line_item(self, payload: dict[str, object]) -> None:
        line_item_id = int(payload["id"])
        status = str(payload.get("review_status", "needs_review"))
        if status not in {"needs_review", "approved", "rejected"}:
            raise ValueError("Invalid line-item status")

        def number_or_none(value: object) -> float | None:
            if value in (None, ""):
                return None
            return float(value)

        with self.connect() as connection:
            connection.execute(
                """
                UPDATE line_items
                SET raw_description = ?,
                    quantity_raw = ?,
                    quantity_value = ?,
                    quantity_unit = ?,
                    unit_price = ?,
                    amount = ?,
                    review_status = ?
                WHERE id = ?
                """,
                (
                    str(payload.get("raw_description", "")),
                    str(payload.get("quantity_raw", "")),
                    number_or_none(payload.get("quantity_value")),
                    str(payload.get("quantity_unit", "")),
                    number_or_none(payload.get("unit_price")),
                    number_or_none(payload.get("amount")),
                    status,
                    line_item_id,
                ),
            )
            connection.commit()

    def update_issue(self, payload: dict[str, object]) -> None:
        issue_id = int(payload["id"])
        resolved = 1 if int(payload.get("resolved", 0)) else 0
        notes = str(payload.get("notes", ""))
        with self.connect() as connection:
            connection.execute(
                "UPDATE review_issues SET resolved = ?, notes = ? WHERE id = ?",
                (resolved, notes, issue_id),
            )
            connection.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local review dashboard for procurement prototype data.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")
    ReviewServer.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), ReviewServer)
    print(f"Review dashboard: http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
