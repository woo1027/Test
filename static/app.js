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
  const hoursList = document.getElementById("hours-list");
  const bentoSalesList = document.getElementById("bento-sales-list");
  const incomeCategorySelect = document.getElementById("income-category");
  const incomeAmount = document.getElementById("income-amount");
  const incomeNote = document.getElementById("income-note");
  const incomeList = document.getElementById("income-list");
  const incomeTotal = document.getElementById("income-total");

  async function loadCategories() {
    const cats = await apiGet("/api/categories");
    categorySelect.innerHTML = cats
      .filter((c) => !c.is_payroll_category)
      .map((c) => `<option value="${c.id}">${c.name}</option>`)
      .join("");
  }

  async function loadIncomeCategories() {
    const cats = await apiGet("/api/income_categories");
    incomeCategorySelect.innerHTML = cats
      .map((c) => `<option value="${c.id}">${c.name}</option>`)
      .join("");
  }

  async function loadIncome() {
    const rows = await apiGet(`/api/income?date=${dateInput.value}`);
    incomeList.innerHTML = "";
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
        await apiSend(`/api/income/${r.id}`, "DELETE");
        loadIncome();
      });
      incomeList.appendChild(tr);
    });
    incomeTotal.textContent = fmt(total);
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

  async function loadHours() {
    const rows = await apiGet(`/api/work_hours?date=${dateInput.value}`);
    hoursList.innerHTML = rows
      .map(
        (r) => `
        <tr data-employee-id="${r.employee_id}">
          <td>${r.name}</td>
          <td>${fmt(r.hourly_rate)}</td>
          <td><input type="number" class="hours-input" min="0" step="0.5" value="${r.hours ?? ""}" style="min-width:80px" /></td>
          <td><button class="link-btn save-hours-btn">儲存</button></td>
        </tr>`
      )
      .join("");

    hoursList.querySelectorAll("tr").forEach((tr) => {
      const employeeId = Number(tr.dataset.employeeId);
      tr.querySelector(".save-hours-btn").addEventListener("click", async () => {
        const hours = tr.querySelector(".hours-input").value;
        if (hours === "") {
          alert("請輸入時數");
          return;
        }
        try {
          await apiSend("/api/work_hours", "POST", {
            date: dateInput.value,
            employee_id: employeeId,
            hours,
          });
          loadTodayComputation();
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  async function loadBentoSales() {
    const rows = await apiGet(`/api/bento_sales?date=${dateInput.value}`);
    bentoSalesList.innerHTML = rows
      .map(
        (r) => `
        <tr data-bento-item-id="${r.bento_item_id}">
          <td>${r.name}</td>
          <td><input type="number" class="bento-qty-input" min="0" step="1" value="${r.quantity ?? ""}" style="min-width:80px" /></td>
          <td><button class="link-btn save-bento-qty-btn">儲存</button></td>
        </tr>`
      )
      .join("");

    bentoSalesList.querySelectorAll("tr").forEach((tr) => {
      const bentoItemId = Number(tr.dataset.bentoItemId);
      tr.querySelector(".save-bento-qty-btn").addEventListener("click", async () => {
        const quantity = tr.querySelector(".bento-qty-input").value;
        if (quantity === "") {
          alert("請輸入數量");
          return;
        }
        try {
          await apiSend("/api/bento_sales", "POST", {
            date: dateInput.value,
            bento_item_id: bentoItemId,
            quantity,
          });
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  async function loadRecent() {
    const rows = await apiGet("/api/recent?days=14");
    recentList.innerHTML = rows
      .map(
        (r) => `
        <tr>
          <td>${r.date}</td>
          <td>${fmt(r.register_revenue)}</td>
          <td>${fmt(r.special_income)}</td>
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
      loadTodayComputation();
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
      loadTodayComputation();
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById("add-income-btn").addEventListener("click", async () => {
    if (!incomeAmount.value) {
      alert("請輸入金額");
      return;
    }
    try {
      await apiSend("/api/income", "POST", {
        date: dateInput.value,
        category_id: Number(incomeCategorySelect.value),
        amount: incomeAmount.value,
        note: incomeNote.value,
      });
      incomeAmount.value = "";
      incomeNote.value = "";
      loadIncome();
      loadRecent();
      loadTodayComputation();
    } catch (e) {
      alert(e.message);
    }
  });

  async function loadTodayComputation() {
    const data = await apiGet(`/api/report/daily?date=${dateInput.value}`);

    document.getElementById("today-summary-grid").innerHTML = `
      <div class="summary-item"><div class="label">當日營業額</div><div class="value">${fmt(data.register_revenue)}</div></div>
      <div class="summary-item"><div class="label">當日特別收入</div><div class="value">${fmt(data.special_income)}</div></div>
      <div class="summary-item"><div class="label">當日總收入</div><div class="value">${fmt(data.revenue)}</div></div>
      <div class="summary-item"><div class="label">可算日成本小計</div><div class="value">${fmt(data.computable_subtotal)}</div></div>
    `;

    document.getElementById("today-computable-list").innerHTML = data.computable_costs
      .map((c) => {
        const mainRow = `<tr><td><strong>${c.name}</strong></td><td><strong>${fmt(c.amount)}</strong></td><td>${c.note}</td></tr>`;
        if (!c.breakdown) return mainRow;
        const subRows = c.breakdown
          .map(
            (b) => `
            <tr class="breakdown-row">
              <td style="padding-left:1.6rem; color:var(--muted);">${b.name}（${b.employee_type}）</td>
              <td>${fmt(b.amount)}</td>
              <td style="color:var(--muted); font-size:0.9em;">${b.note}</td>
            </tr>`
          )
          .join("");
        return mainRow + subRows;
      })
      .join("");
    document.getElementById("today-computable-total").textContent = fmt(data.computable_subtotal);

    document.getElementById("today-reference-list").innerHTML = data.reference_costs
      .map((c) => `<tr><td>${c.name}</td><td>${fmt(c.amount_today)}</td></tr>`)
      .join("");
  }

  document.getElementById("recalc-today-btn").addEventListener("click", loadTodayComputation);

  dateInput.addEventListener("change", () => {
    loadRevenue();
    loadCosts();
    loadIncome();
    loadHours();
    loadBentoSales();
    loadTodayComputation();
  });

  (async () => {
    await loadCategories();
    await loadIncomeCategories();
    await loadRevenue();
    await loadCosts();
    await loadIncome();
    await loadHours();
    await loadBentoSales();
    await loadRecent();
    await loadTodayComputation();
  })();
}

// ---------------- 月報表頁 ----------------

let dailyChartInstance = null;

function initReportPage() {
  const viewMode = document.getElementById("view-mode");
  const monthField = document.getElementById("month-field");
  const dayField = document.getElementById("day-field");
  const monthInput = document.getElementById("report-month");
  const dateInput = document.getElementById("report-date");
  const monthView = document.getElementById("month-view");
  const dayView = document.getElementById("day-view");

  const summaryGrid = document.getElementById("summary-grid");
  const foodStandardSummary = document.getElementById("food-standard-summary");
  const foodStandardList = document.getElementById("food-standard-list");
  const packagingStandardSummary = document.getElementById("packaging-standard-summary");
  const revenueCheckSummary = document.getElementById("revenue-check-summary");
  const breakdownList = document.getElementById("cost-breakdown-list");

  function renderStandardSummary(el, s) {
    const exceeded = s.difference > 0;
    el.innerHTML = `
      <div class="summary-item"><div class="label">標準成本（理論）</div><div class="value">${fmt(s.theoretical_cost)}</div></div>
      <div class="summary-item"><div class="label">實際花費</div><div class="value">${fmt(s.actual_cost)}</div></div>
      <div class="summary-item"><div class="label">差異</div><div class="value">${fmt(s.difference)}</div></div>
      <div class="summary-item">
        <div class="label">狀態</div>
        <div class="value">${
          exceeded
            ? '<span class="badge badge-warn">實際高於標準</span>'
            : '<span class="badge badge-ok">在標準內</span>'
        }</div>
      </div>
    `;
  }

  async function loadMonthlyReport() {
    const data = await apiGet(`/api/report/monthly?month=${monthInput.value}`);

    summaryGrid.innerHTML = `
      <div class="summary-item"><div class="label">營業額</div><div class="value">${fmt(data.register_revenue)}</div></div>
      <div class="summary-item"><div class="label">特別收入</div><div class="value">${fmt(data.special_income)}</div></div>
      <div class="summary-item"><div class="label">總收入</div><div class="value">${fmt(data.revenue)}</div></div>
      <div class="summary-item"><div class="label">總成本</div><div class="value">${fmt(data.total_cost)}</div></div>
      <div class="summary-item"><div class="label">利潤</div><div class="value">${fmt(data.profit)}</div></div>
      <div class="summary-item"><div class="label">利潤率</div><div class="value">${data.profit_margin}%</div></div>
    `;

    const rc = data.revenue_check;
    const underCollected = rc.difference < 0;
    revenueCheckSummary.innerHTML = `
      <div class="summary-item"><div class="label">理論營業額</div><div class="value">${fmt(rc.theoretical_revenue)}</div></div>
      <div class="summary-item"><div class="label">實際營業額</div><div class="value">${fmt(rc.actual_revenue)}</div></div>
      <div class="summary-item"><div class="label">差異</div><div class="value">${fmt(rc.difference)}</div></div>
      <div class="summary-item">
        <div class="label">狀態</div>
        <div class="value">${
          underCollected
            ? '<span class="badge badge-warn">實際低於理論</span>'
            : '<span class="badge badge-ok">實際≥理論</span>'
        }</div>
      </div>
    `;

    const fs = data.food_standard;
    renderStandardSummary(foodStandardSummary, fs);
    renderStandardSummary(packagingStandardSummary, data.packaging_standard);
    foodStandardList.innerHTML = fs.items
      .map(
        (i) => `
        <tr>
          <td>${i.name}</td>
          <td>${fmt(i.quantity)}</td>
          <td>${fmt(i.standard_cost_per_unit)}</td>
          <td>${fmt(i.theoretical_cost)}</td>
        </tr>`
      )
      .join("");

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

  async function loadDailyReport() {
    const data = await apiGet(`/api/report/daily?date=${dateInput.value}`);

    document.getElementById("day-summary-grid").innerHTML = `
      <div class="summary-item"><div class="label">當日營業額</div><div class="value">${fmt(data.register_revenue)}</div></div>
      <div class="summary-item"><div class="label">當日特別收入</div><div class="value">${fmt(data.special_income)}</div></div>
      <div class="summary-item"><div class="label">當日總收入</div><div class="value">${fmt(data.revenue)}</div></div>
      <div class="summary-item"><div class="label">可算日成本小計</div><div class="value">${fmt(data.computable_subtotal)}</div></div>
      <div class="summary-item"><div class="label">當月天數</div><div class="value">${data.days_in_month}</div></div>
    `;

    document.getElementById("day-computable-list").innerHTML = data.computable_costs
      .map((c) => {
        const mainRow = `<tr><td><strong>${c.name}</strong></td><td><strong>${fmt(c.amount)}</strong></td><td>${c.note}</td></tr>`;
        if (!c.breakdown) return mainRow;
        const subRows = c.breakdown
          .map(
            (b) => `
            <tr class="breakdown-row">
              <td style="padding-left:1.6rem; color:var(--muted);">${b.name}（${b.employee_type}）</td>
              <td>${fmt(b.amount)}</td>
              <td style="color:var(--muted); font-size:0.9em;">${b.note}</td>
            </tr>`
          )
          .join("");
        return mainRow + subRows;
      })
      .join("");
    document.getElementById("day-computable-total").textContent = fmt(data.computable_subtotal);

    document.getElementById("day-reference-list").innerHTML = data.reference_costs
      .map((c) => `<tr><td>${c.name}</td><td>${fmt(c.amount_today)}</td></tr>`)
      .join("");
  }

  function applyViewMode() {
    const isDay = viewMode.value === "day";
    dayField.hidden = !isDay;
    monthField.hidden = isDay;
    dayView.hidden = !isDay;
    monthView.hidden = isDay;
  }

  document.getElementById("load-report-btn").addEventListener("click", () => {
    applyViewMode();
    if (viewMode.value === "day") loadDailyReport();
    else loadMonthlyReport();
  });
  viewMode.addEventListener("change", applyViewMode);

  applyViewMode();
  loadMonthlyReport();
}

// ---------------- 設定頁 ----------------

function initSettingsPage() {
  const list = document.getElementById("category-list");

  async function loadCategories() {
    const cats = await apiGet("/api/categories?active=0");
    list.innerHTML = cats
      .map((c) => {
        return `
        <tr data-id="${c.id}">
          <td><input type="text" class="cat-name" value="${c.name}" ${c.is_active ? "" : "disabled"} /></td>
          <td><input type="number" class="cat-target" value="${c.target_percent}" min="0" step="0.1" style="min-width:80px" ${c.is_active ? "" : "disabled"} /></td>
          <td>
            <select class="cat-daily" ${c.is_active ? "" : "disabled"}>
              <option value="0" ${c.daily_computable ? "" : "selected"}>否</option>
              <option value="1" ${c.daily_computable ? "selected" : ""}>是</option>
            </select>
          </td>
          <td>${c.is_active ? '<span class="badge badge-ok">啟用中</span>' : '<span class="badge badge-warn">已停用</span>'}</td>
          <td>
            <button class="link-btn save-btn">儲存</button>
            <button class="link-btn del-btn">${c.is_active ? "刪除" : ""}</button>
          </td>
        </tr>`;
      })
      .join("");

    list.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/categories/${id}`, "PUT", {
            name: tr.querySelector(".cat-name").value,
            target_percent: tr.querySelector(".cat-target").value,
            daily_computable: tr.querySelector(".cat-daily").value === "1",
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
    const dailyComputable = document.getElementById("new-cat-daily-computable").value === "1";
    if (!name) {
      alert("請輸入項目名稱");
      return;
    }
    try {
      await apiSend("/api/categories", "POST", { name, target_percent: target, daily_computable: dailyComputable });
      document.getElementById("new-cat-name").value = "";
      document.getElementById("new-cat-target").value = "";
      document.getElementById("new-cat-daily-computable").value = "0";
      loadCategories();
    } catch (e) {
      alert(e.message);
    }
  });

  loadCategories();

  const incomeList = document.getElementById("income-category-list");

  async function loadIncomeCategories() {
    const cats = await apiGet("/api/income_categories?active=0");
    incomeList.innerHTML = cats
      .map(
        (c) => `
        <tr data-id="${c.id}">
          <td><input type="text" class="income-cat-name" value="${c.name}" ${c.is_active ? "" : "disabled"} /></td>
          <td>${c.is_active ? '<span class="badge badge-ok">啟用中</span>' : '<span class="badge badge-warn">已停用</span>'}</td>
          <td>
            <button class="link-btn save-income-cat-btn">儲存</button>
            <button class="link-btn del-income-cat-btn">${c.is_active ? "刪除" : ""}</button>
          </td>
        </tr>`
      )
      .join("");

    incomeList.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-income-cat-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/income_categories/${id}`, "PUT", {
            name: tr.querySelector(".income-cat-name").value,
          });
          loadIncomeCategories();
        } catch (e) {
          alert(e.message);
        }
      });
      const delBtn = tr.querySelector(".del-income-cat-btn");
      if (delBtn && delBtn.textContent) {
        delBtn.addEventListener("click", async () => {
          if (!confirm("確定要刪除／停用此項目嗎？")) return;
          const data = await apiSend(`/api/income_categories/${id}`, "DELETE");
          alert(data.message);
          loadIncomeCategories();
        });
      }
    });
  }

  document.getElementById("add-income-cat-btn").addEventListener("click", async () => {
    const name = document.getElementById("new-income-cat-name").value.trim();
    if (!name) {
      alert("請輸入項目名稱");
      return;
    }
    try {
      await apiSend("/api/income_categories", "POST", { name });
      document.getElementById("new-income-cat-name").value = "";
      loadIncomeCategories();
    } catch (e) {
      alert(e.message);
    }
  });

  loadIncomeCategories();
}

// ---------------- 人事設定頁 ----------------

function initStaffPage() {
  const list = document.getElementById("employee-list");

  async function loadEmployees() {
    const emps = await apiGet("/api/employees?active=0");
    list.innerHTML = emps
      .map(
        (e) => `
        <tr data-id="${e.id}">
          <td><input type="text" class="emp-name" value="${e.name}" ${e.is_active ? "" : "disabled"} /></td>
          <td>
            <select class="emp-type" ${e.is_active ? "" : "disabled"}>
              <option value="正職" ${e.employee_type === "正職" ? "selected" : ""}>正職</option>
              <option value="計時" ${e.employee_type === "計時" ? "selected" : ""}>計時</option>
            </select>
          </td>
          <td><input type="number" class="emp-salary" min="0" step="1" value="${e.monthly_salary ?? ""}" style="min-width:90px" ${e.is_active ? "" : "disabled"} /></td>
          <td><input type="number" class="emp-rate" min="0" step="1" value="${e.hourly_rate ?? ""}" style="min-width:80px" ${e.is_active ? "" : "disabled"} /></td>
          <td>${e.is_active ? '<span class="badge badge-ok">在職</span>' : '<span class="badge badge-warn">已停用</span>'}</td>
          <td>
            <button class="link-btn save-btn">儲存</button>
            <button class="link-btn del-btn">${e.is_active ? "刪除" : ""}</button>
          </td>
        </tr>`
      )
      .join("");

    list.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/employees/${id}`, "PUT", {
            name: tr.querySelector(".emp-name").value,
            employee_type: tr.querySelector(".emp-type").value,
            monthly_salary: tr.querySelector(".emp-salary").value,
            hourly_rate: tr.querySelector(".emp-rate").value,
          });
          loadEmployees();
        } catch (e) {
          alert(e.message);
        }
      });
      const delBtn = tr.querySelector(".del-btn");
      if (delBtn && delBtn.textContent) {
        delBtn.addEventListener("click", async () => {
          if (!confirm("確定要刪除／停用此員工嗎？")) return;
          const data = await apiSend(`/api/employees/${id}`, "DELETE");
          alert(data.message);
          loadEmployees();
        });
      }
    });
  }

  document.getElementById("add-emp-btn").addEventListener("click", async () => {
    const name = document.getElementById("new-emp-name").value.trim();
    const employee_type = document.getElementById("new-emp-type").value;
    const monthly_salary = document.getElementById("new-emp-salary").value;
    const hourly_rate = document.getElementById("new-emp-rate").value;
    if (!name) {
      alert("請輸入姓名");
      return;
    }
    try {
      await apiSend("/api/employees", "POST", { name, employee_type, monthly_salary, hourly_rate });
      document.getElementById("new-emp-name").value = "";
      document.getElementById("new-emp-salary").value = "";
      document.getElementById("new-emp-rate").value = "";
      loadEmployees();
    } catch (e) {
      alert(e.message);
    }
  });

  loadEmployees();
}

// ---------------- 標準成本頁 ----------------

function initRecipePage() {
  const ingredientList = document.getElementById("ingredient-list");
  const bentoList = document.getElementById("bento-list");
  const bentoMarginList = document.getElementById("bento-margin-list");

  async function loadIngredients() {
    const ings = await apiGet("/api/ingredients");
    ingredientList.innerHTML = ings
      .map(
        (i) => `
        <tr data-id="${i.id}">
          <td>${i.name}</td>
          <td>${i.category === "packaging" ? '<span class="badge badge-neutral">包材</span>' : "食材"}</td>
          <td>${i.unit}</td>
          <td><input type="number" class="ing-cost" value="${i.unit_cost}" min="0" step="0.01" style="min-width:90px" /></td>
          <td><button class="link-btn save-ing-btn">儲存</button></td>
        </tr>`
      )
      .join("");

    ingredientList.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-ing-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/ingredients/${id}`, "PUT", {
            unit_cost: tr.querySelector(".ing-cost").value,
          });
          loadIngredients();
          loadBentoItems();
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  async function loadBentoItems() {
    const items = await apiGet("/api/bento_items");

    bentoMarginList.innerHTML = items
      .map(
        (item) => `
        <tr data-id="${item.id}">
          <td>${item.name}</td>
          <td>${fmt(item.standard_cost)}</td>
          <td><input type="number" class="bento-price" value="${item.selling_price}" min="0" step="1" style="min-width:80px" /></td>
          <td>${fmt(item.margin)}</td>
          <td>${item.margin_percent}%</td>
          <td><button class="link-btn save-price-btn">儲存</button></td>
        </tr>`
      )
      .join("");

    bentoMarginList.querySelectorAll("tr").forEach((tr) => {
      const id = tr.dataset.id;
      tr.querySelector(".save-price-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/bento_items/${id}`, "PUT", {
            selling_price: tr.querySelector(".bento-price").value,
          });
          loadBentoItems();
        } catch (e) {
          alert(e.message);
        }
      });
    });

    bentoList.innerHTML = items
      .map(
        (item) => `
        <div class="card" style="margin-top:1rem;">
          <h3 style="margin:0 0 0.6rem;">${item.name} <span class="hint">標準成本：<strong id="bento-cost-${item.id}">${fmt(item.standard_cost)}</strong></span></h3>
          <table class="data-table">
            <thead><tr><th>食材</th><th>用量</th><th>單位</th><th></th></tr></thead>
            <tbody>
              ${item.recipe
                .map(
                  (r) => `
                <tr data-recipe-id="${r.id}" data-bento-id="${item.id}">
                  <td>${r.ingredient_name}</td>
                  <td><input type="number" class="recipe-qty" value="${r.quantity}" min="0" step="0.1" style="min-width:80px" /></td>
                  <td>${r.unit}</td>
                  <td><button class="link-btn save-recipe-btn">儲存</button></td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>`
      )
      .join("");

    bentoList.querySelectorAll("tr[data-recipe-id]").forEach((tr) => {
      const recipeId = tr.dataset.recipeId;
      tr.querySelector(".save-recipe-btn").addEventListener("click", async () => {
        try {
          await apiSend(`/api/bento_recipe/${recipeId}`, "PUT", {
            quantity: tr.querySelector(".recipe-qty").value,
          });
          loadBentoItems();
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  loadIngredients();
  loadBentoItems();
}
