const tg = window.Telegram?.WebApp;
const CURRENCIES = ["RUB", "USD", "EUR", "KZT", "GBP", "TRY", "GEL", "AMD", "UAH", "BYN", "CNY", "AED", "THB"];
const SIGNS = { RUB: "₽", USD: "$", EUR: "€", KZT: "₸", GBP: "£", UAH: "₴", GEL: "₾", TRY: "₺" };
const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#64748b", "#111827", "#facc15"];
const UNIT = { day: ["день", "дня", "дней"], week: ["неделя", "недели", "недель"], month: ["месяц", "месяца", "месяцев"], year: ["год", "года", "лет"] };

let state = null;
let tab = "subs";
let editing = null; // {kind, id}

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const plural = (n, [one, few, many]) => (n % 10 === 1 && n % 100 !== 11 ? one : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? few : many);
const money = (v, cur) => `${Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ${SIGNS[cur] || cur}`;
const parseDays = (s) => [...new Set(String(s).split(/[,\s]+/).filter(Boolean).map(Number))].filter((n) => Number.isInteger(n) && n >= 0 && n <= 90);
const haptic = (t = "light") => tg?.HapticFeedback?.impactOccurred?.(t);

function when(days) {
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  return `через ${days} ${plural(days, ["день", "дня", "дней"])}`;
}
function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}
function period(s) {
  return s.every === 1 ? `раз в ${{ day: "день", week: "неделю", month: "месяц", year: "год" }[s.unit]}` : `каждые ${s.every} ${plural(s.every, UNIT[s.unit])}`;
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", Authorization: "tma " + (tg?.initData || "") },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 || res.status === 403) {
    denied(res.status === 403 ? `Доступ к боту закрыт. Твой ID: ${tg?.initDataUnsafe?.user?.id ?? "?"} — отправь его владельцу.` : "Открой приложение из Telegram-бота.");
    throw new Error("denied");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = Array.isArray(err.detail) ? err.detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("\n") : err.detail || res.statusText;
    alertMsg("Ошибка: " + msg);
    throw new Error(msg);
  }
  return res.json();
}

function alertMsg(text) {
  tg?.showAlert ? tg.showAlert(text) : alert(text);
}
function confirmMsg(text) {
  return new Promise((r) => (tg?.showConfirm ? tg.showConfirm(text, r) : r(confirm(text))));
}
function denied(text) {
  $("#denied-text").textContent = text;
  $("#denied").hidden = false;
}

async function load() {
  state = await api("GET", "/api/state");
  render();
}

function render() {
  const m = Object.entries(state.monthly);
  $("#summary").innerHTML = m.length
    ? `<span class="label">В месяц ≈</span>` + m.map(([c, v]) => `<span class="chip">${esc(money(v, c))}</span>`).join("")
    : `<span class="label">Подписок пока нет</span>`;

  const cards = Object.fromEntries(state.cards.map((c) => [c.id, c]));
  $("#subs-list").innerHTML = state.subs.length
    ? state.subs
        .map((s) => {
          const c = cards[s.card_id];
          const sub = [c ? `${esc(c.name)}${c.last4 ? " •" + esc(c.last4) : ""}` : "без карты", period(s)].join(" · ");
          return `<button class="item ${s.active ? "" : "off"}" data-sub="${s.id}">
            <span class="dot" style="background:${c ? esc(c.color) : ""}"></span>
            <span class="main"><div class="name">${esc(s.name)}</div><div class="sub">${sub}</div></span>
            <span class="right"><div class="amount">${esc(money(s.amount, s.currency))}</div>
              <div class="when ${s.active && s.days_left <= 3 ? "soon" : ""}">${s.active ? `${fmtDate(s.next_charge)}, ${when(s.days_left)}` : "на паузе"}</div></span>
          </button>`;
        })
        .join("")
    : `<div class="empty">Нажми «+», чтобы добавить первую подписку.<br>Карты можно завести на вкладке «Карты».</div>`;

  $("#cards-list").innerHTML = state.cards.length
    ? state.cards
        .map((c) => {
          const n = state.subs.filter((s) => s.card_id === c.id).length;
          return `<button class="item" data-card="${c.id}">
            <span class="cardface" style="background:${esc(c.color)}"></span>
            <span class="main"><div class="name">${esc(c.name)}</div><div class="sub">${c.last4 ? "•• " + esc(c.last4) + " · " : ""}${n} ${plural(n, ["подписка", "подписки", "подписок"])}</div></span>
          </button>`;
        })
        .join("")
    : `<div class="empty">Карт пока нет. Нажми «+».</div>`;

  const f = $("#settings-form");
  if (document.activeElement?.form !== f) {
    f.tz.value = state.me.tz;
    f.notify_time.value = state.me.notify_time;
    f.default_reminders.value = state.me.default_reminders.join(", ");
  }
  $("#fab").hidden = tab === "settings";
}

function setTab(t) {
  tab = t;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === "tab-" + t));
  $("#fab").hidden = t === "settings";
}

// --- sheets ---

function openSheet(id) {
  $("#backdrop").hidden = false;
  $(id).hidden = false;
  tg?.BackButton?.show();
}
function closeSheets() {
  $("#backdrop").hidden = true;
  document.querySelectorAll(".sheet").forEach((s) => (s.hidden = true));
  tg?.BackButton?.hide();
  editing = null;
}

function openSub(id) {
  const s = state.subs.find((x) => x.id === id);
  editing = { kind: "sub", id: s?.id ?? null };
  const f = $("#sub-form");
  $("#sub-title").textContent = s ? "Подписка" : "Новая подписка";
  f.card_id.innerHTML = `<option value="">— без карты —</option>` + state.cards.map((c) => `<option value="${c.id}">${esc(c.name)}${c.last4 ? " •" + esc(c.last4) : ""}</option>`).join("");
  f.name.value = s?.name ?? "";
  f.amount.value = s?.amount ?? "";
  f.currency.value = s?.currency ?? (state.subs[0]?.currency || "RUB");
  f.card_id.value = s?.card_id ?? (state.cards.length === 1 ? state.cards[0].id : "");
  f.anchor.value = s?.next_charge ?? state.today;
  // показываем ближайшую дату, но если её не трогали — сохраняем исходный якорь (31-е число не «съедет» на 28-е)
  f.anchor.dataset.shown = f.anchor.value;
  f.anchor.dataset.orig = s?.anchor ?? "";
  f.anchor.dataset.period = s ? `${s.every}:${s.unit}` : "";
  f.every.value = s?.every ?? 1;
  f.unit.value = s?.unit ?? "month";
  f.custom_rem.checked = s ? s.reminders !== null : false;
  f.reminders.value = (s?.reminders ?? state.me.default_reminders).join(", ");
  $("#rem-wrap").hidden = !f.custom_rem.checked;
  f.note.value = s?.note ?? "";
  f.active.checked = s ? s.active : true;
  $("#sub-delete").hidden = !s;
  openSheet("#sub-sheet");
  if (!s) f.name.focus();
}

function openCard(id) {
  const c = state.cards.find((x) => x.id === id);
  editing = { kind: "card", id: c?.id ?? null };
  const f = $("#card-form");
  $("#card-title").textContent = c ? "Карта" : "Новая карта";
  f.name.value = c?.name ?? "";
  f.last4.value = c?.last4 ?? "";
  pickColor(c?.color ?? COLORS[state.cards.length % COLORS.length]);
  $("#card-delete").hidden = !c;
  openSheet("#card-sheet");
}

function pickColor(color) {
  $("#card-form").color.value = color;
  $("#swatches").innerHTML = COLORS.map((c) => `<button type="button" data-color="${c}" class="${c === color ? "sel" : ""}" style="background:${c}"></button>`).join("");
}

// --- events ---

document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
$("#fab").addEventListener("click", () => (tab === "cards" ? openCard(null) : openSub(null)));
$("#backdrop").addEventListener("click", closeSheets);
tg?.BackButton?.onClick(closeSheets);
$("#subs-list").addEventListener("click", (e) => {
  const el = e.target.closest("[data-sub]");
  if (el) openSub(Number(el.dataset.sub));
});
$("#cards-list").addEventListener("click", (e) => {
  const el = e.target.closest("[data-card]");
  if (el) openCard(Number(el.dataset.card));
});
$("#swatches").addEventListener("click", (e) => {
  const el = e.target.closest("[data-color]");
  if (el) pickColor(el.dataset.color);
});
$("#sub-form").custom_rem.addEventListener("change", (e) => ($("#rem-wrap").hidden = !e.target.checked));

// исходный якорь сохраняем, только если не меняли ни дату, ни период — иначе показанная дата и есть новый якорь
function keepAnchor(f) {
  const d = f.anchor.dataset;
  return d.orig && f.anchor.value === d.shown && `${f.every.value}:${f.unit.value}` === d.period;
}

// блокирует кнопку отправки на время запроса — двойной тап не создаст дубль
function guarded(handler) {
  return async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    if (btn.disabled) return;
    btn.disabled = true;
    try {
      await handler(e);
    } catch {
      // ошибку уже показал api()
    } finally {
      btn.disabled = false;
    }
  };
}

$("#sub-form").addEventListener("submit", guarded(async (e) => {
  const f = e.target;
  const amount = Number(String(f.amount.value).replace(",", ".").replace(/\s/g, ""));
  if (!(amount > 0)) return alertMsg("Сумма должна быть больше нуля");
  const body = {
    name: f.name.value.trim(),
    amount,
    currency: f.currency.value.trim().toUpperCase(),
    card_id: f.card_id.value ? Number(f.card_id.value) : null,
    anchor: keepAnchor(f) ? f.anchor.dataset.orig : f.anchor.value,
    unit: f.unit.value,
    every: Number(f.every.value),
    reminders: f.custom_rem.checked ? parseDays(f.reminders.value) : null,
    note: f.note.value.trim(),
    active: f.active.checked,
  };
  if (editing.id) await api("PUT", `/api/subs/${editing.id}`, body);
  else await api("POST", "/api/subs", body);
  haptic("medium");
  closeSheets();
  load();
}));

$("#card-form").addEventListener("submit", guarded(async (e) => {
  const f = e.target;
  const body = { name: f.name.value.trim(), last4: f.last4.value.trim(), color: f.color.value };
  if (editing.id) await api("PUT", `/api/cards/${editing.id}`, body);
  else await api("POST", "/api/cards", body);
  haptic("medium");
  closeSheets();
  load();
}));

$("#sub-delete").addEventListener("click", async () => {
  if (!(await confirmMsg("Удалить подписку?"))) return;
  await api("DELETE", `/api/subs/${editing.id}`);
  closeSheets();
  load();
});
$("#card-delete").addEventListener("click", async () => {
  if (!(await confirmMsg("Удалить карту? Подписки останутся, но без карты."))) return;
  await api("DELETE", `/api/cards/${editing.id}`);
  closeSheets();
  load();
});

$("#settings-form").addEventListener("submit", guarded(async (e) => {
  const f = e.target;
  await api("PUT", "/api/settings", { tz: f.tz.value.trim(), notify_time: f.notify_time.value, default_reminders: parseDays(f.default_reminders.value) });
  haptic("medium");
  tg?.showPopup ? tg.showPopup({ message: "Сохранено" }) : null;
  load();
}));
$("#tz-detect").addEventListener("click", () => ($("#settings-form").tz.value = Intl.DateTimeFormat().resolvedOptions().timeZone));

// --- init ---

$("#cur-list").innerHTML = CURRENCIES.map((c) => `<option value="${c}">`).join("");
try {
  $("#tz-list").innerHTML = Intl.supportedValuesOf("timeZone").map((z) => `<option value="${z}">`).join("");
} catch {}
if (tg) {
  document.documentElement.dataset.tg = "1";
  tg.ready();
  tg.expand();
}
if (!tg?.initData) denied("Открой приложение из Telegram-бота.");
else load().catch(() => {});
