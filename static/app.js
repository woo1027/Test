async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json()).error || "讀取失敗");
  return res.json();
}

async function apiSend(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "操作失敗");
  return data;
}

function fmt(n) {
  return Number(n || 0).toLocaleString("zh-Hant-TW", { maximumFractionDigits: 0 });
}

// ---------------- 每日紀錄頁 ----------------

function initDailyPage() {
  const dateInput = document.getElementById("record-date");
  const revenueInput = document.getElementById("revenue-input");
  const categorySelect = document.getElementById("cost-category");
  const costAmount = document.getElementById("cost-amount");
  const costNote = document.getElementById("cost-note");
  const costList = document.getElementById("cost-list");
  const costTotal = document.getElementById("cost-total");
  const recentList = document.getElementById("recent-list");

  async function loadCategories() {
    const cats = await apiGet("/api/categories");
    categorySelect.innerHTML = cats
      .map((c) => `<option value="${c.id}">${c.name}</option>`)
      .join("");
  }

  async function loadRevenue() {
    const data = await apiGet(`/api/sales?date=${dateInput.value}`);
    revenueInput.value = data.revenue || "";
  }

  async function loadCosts() {
    const rows = await apiGet(`/api/costs?date=${dateInput.value}`);
    costList.innerHTML = "";
    let total = 0;
    rows.forEach((r) => {
      total += r.amount;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.category_name}</td>
        <td>${fmt(r.amount)}</td>
        <td>${r.note || ""}</td>
        <td><button class="link-btn" data-id="${r.id}">刪除</button></td>
      `;
      tr.querySelector("button").addEventListener("click", async () => {
        await apiSend(`/api/costs/${r.id}`, "DELETE");
        loadCosts();
      });
      costList.appendChild(tr);
    });
    costTotal.textContent = fmt(total);
  }

  async function loadRecent() {
    const rows = await apiGet("/api/recent?days=14");
    recentList.innerHTML = rows
      .map(
        (r) => `
        <tr>
          <td>${r.date}</td>
          <td>${fmt(r.revenue)}</td>
          <td>${fmt(r.cost)}</td>
          <td>${fmt(r.profit)}</td>
        </tr>`
      )
      .join("");
  }

  document.getElementById("save-revenue-btn").addEventListener("click", async () => {
    try {
      await apiSend("/api/sales", "POST", {
        date: dateInput.value,
        revenue: revenueInput.value,
      });
      loadRecent();
      alert("已儲存營業額");
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById("add-cost-btn").addEventListener("click", async () => {
    if (!costAmount.value) {
      alert("請輸入金額");
      return;
    }
    try {
      await apiSend("/api/costs", "POST", {
        date: dateInput.value,
        category_id: Number(categorySelect.value),
        amount: costAmount.value,
        note: costNote.value,
      });
      costAmount.value = "";
      costNote.value = "";
      loadCosts();
      loadRecent();
    } catch (e) {
      alert(e.message);
    }
  });

  dateInput.addEventListener("change", () => {
    loadRevenue();
    loadCosts();
  });

  (async () => {
    await loadCategories();
    await loadRevenue();
    await loadCosts();
    await loadRecent();
  })();
}

// ---------------- 月報表頁 ----------------

let dailyChartInstance = null;

function initReportPage() {
  const monthInput = document.getElementById("report-month");
  const summaryGrid = document.getElementById("summary-grid");
  const breakdownList = document.getElementById("cost-breakdown-list");

  async function loadReport() {
    const data = await apiGet(`/api/report/monthly?month=${monthInput.value}`);

    summaryGrid.innerHTML = `
      <div class="summary-item"><div class="label">總營業額</div><div class="value">${fmt(data.revenue)}</div></div>
      <div class="summary-item"><div class="label">總成本</div><div class="value">${fmt(data.total_cost)}</div></div>
      <div class="summary-item"><div class="label">利潤</div><div class="value">${fmt(data.profit)}</div></div>
      <div class="summary-item"><div class="label">利潤率</div><div class="value">${data.profit_margin}%</div></div>
    `;

    breakdownList.innerHTML = data.cost_breakdown
      .map(
        (c) => `
        <tr class="${c.exceeded ? "row-exceeded" : ""}">
          <td>${c.name}</td>
          <td>${fmt(c.amount)}</td>
          <td>${c.percent}%</td>
          <td>${c.target_percent}%</td>
          <td>${
            c.exceeded
              ? '<span class="badge badge-warn">超過目標</span>'
              : '<span class="badge badge-ok">正常</span>'
          }</td>
        </tr>`
      )
      .join("");

    const ctx = document.getElementById("daily-chart");
    const labels = data.daily.map((d) => d.date.slice(5));
    const revenues = data.daily.map((d) => d.revenue);
    const costs = data.daily.map((d) => d.cost);

    if (dailyChartInstance) dailyChartInstance.destroy();
    dailyChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "營業額", data: revenues, borderColor: "#d98254", tension: 0.2 },
          { label: "成本", data: costs, borderColor: "#8a8a8a", tension: 0.2 },
        ],
      },
      options: { responsive: true, scales: { y: { beginAtZero: true } } },
    });
  }

  document.getElementById("load-report-btn").addEventListener("click", loadReport);
  loadReport();
}

// ---------------- 設定頁 ----------------

function initSettingsPage() {
  const list = document.getElementById("category-list");

  async function loadCategories() {
    const cats = await apiGet("/api/categories?active=0");
    list.innerHTML = cats
      .map(
        (c) => `
        <tr data-id="${c.id}">
          <td><input type="text" class="cat-name" value="${c.name}" ${c.is_active ? "" : "disabled"} /></td>
          <td><input type="number" class="cat-target" value="${c.target_percent}" min="0" step="0.1" style="min-width:80px" ${c.is_active ? "" : "disabled"} /></td>
          <td>${c.is_active ? '<span class="badge badge-ok">啟用中</span>' : '<span class="badge badge-warn">已停用</span>'}</td>
          <td>
            <button class="link-btn save-btn">儲存</button>
            <button class="link-btn del-btn">${c.is_active ? "刪除" : ""}</button>
          </td>
        </tr>`
      )
      .join("");

    list.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/categories/${id}`, "PUT", {
            name: tr.querySelector(".cat-name").value,
            target_percent: tr.querySelector(".cat-target").value,
          });
          loadCategories();
        } catch (e) {
          alert(e.message);
        }
      });
      const delBtn = tr.querySelector(".del-btn");
      if (delBtn && delBtn.textContent) {
        delBtn.addEventListener("click", async () => {
          if (!confirm("確定要刪除／停用此項目嗎？")) return;
          const data = await apiSend(`/api/categories/${id}`, "DELETE");
          alert(data.message);
          loadCategories();
        });
      }
    });
  }

  document.getElementById("add-cat-btn").addEventListener("click", async () => {
    const name = document.getElementById("new-cat-name").value.trim();
    const target = document.getElementById("new-cat-target").value || 0;
    if (!name) {
      alert("請輸入項目名稱");
      return;
    }
    try {
      await apiSend("/api/categories", "POST", { name, target_percent: target });
      document.getElementById("new-cat-name").value = "";
      document.getElementById("new-cat-target").value = "";
      loadCategories();
    } catch (e) {
      alert(e.message);
    }
  });

  loadCategories();
}
