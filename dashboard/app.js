(() => {
  const $ = (sel) => document.querySelector(sel);
  const state = {
    mode: "all",
    source: "",
    category: "",
    academicYear: "2026-2027",
    q: "",
    page: 1,
    pages: 1,
    total: 0,
    selectedId: null,
    selected: null,
    stats: null,
    sources: [],
    dataRevision: null,
    pendingRevision: null,
  };
  let searchTimer = null;
  let toastTimer = null;
  let pollTimer = null;
  let pollInFlight = false;
  let websiteCheckTimer = null;
  let websiteCheckLastStatus = null;

  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (ch) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[ch],
    );
  const short = (value, max = 130) => {
    const s = String(value || "")
      .replace(/\s+/g, " ")
      .trim();
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  };
  function normalizeForOverlap(value) {
    return String(value ?? "")
      .normalize("NFKC")
      .replace(/&(?:amp;)*nbsp;|&#(?:0*160|x0*a0);/gi, " ")
      .replace(/\u00a0/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLocaleLowerCase("vi");
  }
  function summaryRepeatsBody(summary, body) {
    const s = normalizeForOverlap(summary)
      .replace(/(?:\.{3,}|…+)$/u, "")
      .trim();
    const b = normalizeForOverlap(body);
    if (s.length < 80 || !b) return false;
    // Listing excerpts often copy the opening of the full article. Hide only
    // a clearly redundant excerpt, not an independent editorial summary.
    const probe = s.slice(0, Math.min(180, s.length));
    return b.startsWith(probe);
  }
  function richHtmlText(value) {
    const template = document.createElement("template");
    template.innerHTML = String(value || ""); // API has already sanitized this fragment.
    return template.content.textContent || "";
  }
  const fmtDate = (value) => {
    if (!value) return "Chưa rõ ngày đăng";
    const d = new Date(value + "T00:00:00");
    return Number.isNaN(d.getTime())
      ? value
      : new Intl.DateTimeFormat("vi-VN", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
        }).format(d);
  };
  const dateIsUncertain = (a) =>
    !!a.published_at &&
    ["legacy_unverified", "unknown", ""].includes(a.published_at_source || "");
  const sourceNames = (a) =>
    (a.source_names || "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  const firstSource = (a) => sourceNames(a)[0] || "Nguồn chưa rõ";
  const toast = (msg) => {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  };
  async function api(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response
      .json()
      .catch(() => ({ error: "Phản hồi không phải JSON" }));
    if (!response.ok)
      throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }
  function setStatus(text, ok = true) {
    $("#connection-status").textContent = text;
    const dot = document.querySelector(".sidebar-footer .status-dot");
    if (dot) dot.style.background = ok ? "#3fa77b" : "#c46a4d";
  }
  function renderWebsiteCheck(payload) {
    $("#refresh-btn").disabled = false;
  }
  function websiteCheckToast(payload) {
    if (payload.status === "error") {
      toast("Kiểm tra website lỗi: " + payload.error);
      return;
    }
    const report = payload.report || {};
    const changed =
      Number(report.new_articles || 0) +
      Number(report.updated_content || 0) +
      Number(report.linked_duplicate || 0);
    const publish = report.auto_publish;
    const messages = [];
    if ((report.failed_sources || []).length) {
      messages.push("kiểm tra có nguồn lỗi");
    }
    if (publish && publish.status === "error") {
      messages.push("publish lỗi; dữ liệu crawler vẫn đã lưu");
    } else if (publish && publish.status === "missing_token") {
      messages.push("thiếu HUB_WRITE_TOKEN; chưa publish");
    } else if (changed > 0) {
      messages.push(
        `đã kiểm tra · mới ${report.new_articles || 0}, cập nhật ${report.updated_content || 0}`,
      );
    }
    if (messages.length) toast(messages.join(" · "));
  }
  async function pollWebsiteCheck() {
    try {
      const payload = await api("/api/website-check");
      const previousStatus = websiteCheckLastStatus;
      websiteCheckLastStatus = payload.status;
      renderWebsiteCheck(payload);
      if (payload.status === "running") {
        if (websiteCheckTimer === null)
          websiteCheckTimer = window.setTimeout(() => {
            websiteCheckTimer = null;
            pollWebsiteCheck();
          }, 1000);
      } else if (
        payload.status === "completed" &&
        previousStatus === "running"
      ) {
        websiteCheckToast(payload);
      }
    } catch (err) {
      renderWebsiteCheck({ status: "error", error: err.message });
      toast("Kiểm tra website lỗi: " + err.message);
    }
  }
  async function loadStats() {
    const statsParams = new URLSearchParams();
    if (state.academicYear)
      statsParams.set("academic_year", state.academicYear);
    const statsQuery = statsParams.toString();
    state.stats = await api(
      "/api/stats" + (statsQuery ? "?" + statsQuery : ""),
    );
    const availableYears = state.stats.academic_years || [];
    if (state.academicYear && !availableYears.includes(state.academicYear)) {
      // If stored history changed while the dashboard was open, reset both the
      // selector and its counts to all-time rather than showing mismatched data.
      state.academicYear = "";
      state.stats = await api("/api/stats");
    }
    const yearOptions = [
      '<option value="">Từ trước đến nay</option>',
      ...(state.stats.academic_years || []).map(
        (y) => `<option value="${esc(y)}">${esc(y.replace("-", "–"))}</option>`,
      ),
    ].join("");
    $("#academic-year-filter").innerHTML = yearOptions;
    $("#academic-year-filter").value = state.academicYear;
    $("#nav-total").textContent = state.stats.articles;
    $("#nav-unread").textContent = state.stats.unread;
    $("#nav-favorites").textContent = state.stats.favorites;
    $("#nav-review").textContent = state.stats.needs_review;
    $("#mark-all-read").disabled = state.stats.unread === 0;
    state.sources = state.stats.sources || [];
    const options = [
      '<option value="">Tất cả nguồn</option>',
      ...state.sources.map(
        (s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`,
      ),
    ].join("");
    $("#source-filter").innerHTML = options;
    $("#source-filter").value = state.source;
    $("#source-list").innerHTML = state.sources
      .map(
        (s) =>
          `<button class="source-shortcut ${state.source === s.id ? "active" : ""}" data-source="${esc(s.id)}"><span class="mini-dot"></span><span>${esc(s.name)}</span><span class="source-n">${s.articles}</span></button>`,
      )
      .join("");
    setStatus(`${state.sources.length} nguồn · CSDL cục bộ`, true);
  }
  function buildCategories(items) {
    const previous = state.category;
    const set = new Set((state.stats?.categories || []).filter(Boolean));
    // Keep a fallback for databases whose categories are not represented in the stats response.
    items.forEach((a) =>
      (a.source_categories || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((x) => set.add(x)),
    );
    const opts = [
      '<option value="">Mọi danh mục</option>',
      ...Array.from(set)
        .sort((a, b) => a.localeCompare(b, "vi"))
        .map((c) => `<option value="${esc(c)}">${esc(c)}</option>`),
    ].join("");
    $("#sort-category").innerHTML = opts;
    if (set.has(previous)) state.category = previous;
    else state.category = "";
    $("#sort-category").value = state.category;
  }
  function dateMarkup(a) {
    const uncertain = dateIsUncertain(a);
    return `<span class="date-conf"><span class="confidence-dot ${!a.published_at || uncertain ? "unknown" : ""}"></span>${esc(fmtDate(a.published_at))}${uncertain ? " · chưa xác minh" : ""}</span>`;
  }
  function renderList(payload, preserveDetail = false) {
    state.total = payload.total;
    state.pages = payload.pages;
    $("#feed-subcount").textContent =
      `· ${payload.total.toLocaleString("vi-VN")} bài`;
    $("#page-label").textContent = payload.total
      ? `${payload.page}/${payload.pages}`
      : "";
    $("#pagination-label").textContent =
      `Trang ${payload.page} / ${payload.pages}`;
    $("#prev-page").disabled = payload.page <= 1;
    $("#next-page").disabled = payload.page >= payload.pages;
    const heading =
      {
        all: "Tất cả thông báo",
        unread: "Thông báo chưa đọc",
        favorites: "Thông báo đã lưu",
        review: "Thông báo cần kiểm tra",
      }[state.mode] || "Thông báo";
    $("#feed-heading").textContent = heading;
    if (!payload.items.length) {
      $("#feed-list").innerHTML =
        `<div class="empty-state"><div class="empty-icon">⌕</div><strong>Không tìm thấy thông báo</strong><span>Thử từ khóa hoặc bộ lọc khác.</span></div>`;
      if (!preserveDetail && state.selectedId !== null) {
        state.selectedId = null;
        state.selected = null;
        renderEmptyDetail();
      }
      return;
    }
    $("#feed-list").innerHTML = payload.items
      .map((a) => {
        const chosen = state.selectedId === a.id;
        const categories = (
          a.source_categories ||
          a.category ||
          "Chưa phân loại"
        )
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        const summary =
          a.summary ||
          a.content_preview ||
          "Chưa có nội dung trích xuất; mở bài gốc để xem chi tiết.";
        return `<article class="article-card ${chosen ? "selected " : ""}${a.read_at ? "" : "unread"}" data-id="${a.id}" tabindex="0" role="button" aria-label="Mở thông báo ${esc(a.title)}">
        <div class="card-meta"><span class="source-chip">${esc(firstSource(a))}</span><span class="category-chip">${esc(categories[0] || "Chưa phân loại")}</span></div>
        <h3 class="card-title">${esc(a.title)}</h3><p class="card-summary">${esc(short(summary, 190))}</p>
        <div class="card-bottom">${dateMarkup(a)}<span class="card-trailing">${a.is_favorite ? "★" : "›"}</span></div>
      </article>`;
      })
      .join("");
    if (
      !preserveDetail &&
      state.selectedId !== null &&
      !payload.items.some((a) => a.id === state.selectedId)
    ) {
      state.selectedId = null;
      state.selected = null;
      renderEmptyDetail();
    }
  }
  function renderEmptyDetail() {
    $("#detail-panel").innerHTML =
      '<div class="detail-empty"><div class="empty-icon">↖</div><h2>Chọn một thông báo để xem nội dung.</h2></div>';
  }
  function renderDetailCloseButton() {
    return '<button class="detail-close" id="close-detail" type="button" title="Đóng thông báo" aria-label="Đóng thông báo">×</button>';
  }
  async function loadList(preserveDetail = false) {
    $("#feed-list").innerHTML =
      '<div class="loading"><span class="spinner"></span>Đang đọc thông báo…</div>';
    const params = new URLSearchParams({
      page: String(state.page),
      limit: "30",
      mode: state.mode,
    });
    if (state.q) params.set("q", state.q);
    if (state.source) params.set("source", state.source);
    if (state.category) params.set("category", state.category);
    if (state.academicYear) params.set("academic_year", state.academicYear);
    try {
      const payload = await api("/api/articles?" + params.toString());
      buildCategories(payload.items);
      renderList(payload, preserveDetail);
      return true;
    } catch (err) {
      $("#feed-list").innerHTML =
        `<div class="empty-state"><strong>Không tải được thông báo</strong><span>${esc(err.message)}</span></div>`;
      setStatus("Lỗi đọc CSDL", false);
      return false;
    }
  }
  async function pollVersion() {
    if (document.visibilityState !== "visible" || pollInFlight) return;
    pollInFlight = true;
    try {
      const payload = await api("/api/version");
      const revision = Number(payload.data_revision);
      if (!Number.isInteger(revision)) return;
      if (state.dataRevision === null) {
        state.dataRevision = revision;
        state.pendingRevision = null;
      } else if (revision !== state.dataRevision) {
        state.pendingRevision = revision;
      } else {
        state.pendingRevision = null;
      }
    } catch (_) {
      // A transient polling failure must not disturb the current dashboard view.
    } finally {
      pollInFlight = false;
    }
  }
  function startPolling() {
    pollTimer = window.setInterval(pollVersion, 5000);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") pollVersion();
    });
  }
  function richHtmlHasPayload(markup) {
    if (!markup) return false;
    const template = document.createElement("template");
    template.innerHTML = markup;
    return Boolean(
      template.content.textContent.trim() ||
      template.content.querySelector("a[href], img[src], table, ul, ol, dl"),
    );
  }
  function isTascoAnnouncement(links) {
    return (links || []).some((link) =>
      /hcmus\.edu\.vn\/truong-dai-hoc-khoa-hoc-tu-nhien-dhqg-hcm-ky-ket-thoa-thuan-hop-tac-voi-cong-ty-co-phan-tasco(?:[/?#]|$)/i.test(
        link.source_url || "",
      ),
    );
  }
  function scopeTascoLogos(markup) {
    // The source page has two compact logos plus full-size event photographs.
    // Only mark logos inside this exact announcement; ordinary article photos
    // continue to use the existing .rich-content img rules unchanged.
    const template = document.createElement("template");
    template.innerHTML = markup;
    const images = Array.from(template.content.querySelectorAll("img"));
    const filenameOf = (img) => {
      const src = (img.getAttribute("src") || "").split(/[?#]/, 1)[0];
      return src.slice(src.lastIndexOf("/") + 1);
    };
    const isEventPhoto = (img) =>
      /^P4T\d+(?:-scaled)?\.(?:jpe?g|webp)$/i.test(filenameOf(img));
    const logoLike = (img) =>
      /(?:logo|tasco|hcmus|khtn|dhqg)/i.test(
        `${img.getAttribute("src") || ""} ${img.getAttribute("alt") || ""}`,
      );
    const selected = images
      .filter((img) => !isEventPhoto(img) && logoLike(img))
      .slice(0, 2);
    // If the page uses opaque filenames without helpful alt text, use the first
    // two non-event images in this article as the narrow, article-specific fallback.
    for (const img of images) {
      if (selected.length >= 2) break;
      if (!isEventPhoto(img) && !selected.includes(img)) selected.push(img);
    }
    selected.forEach((img) => img.classList.add("tasco-logo-image"));
    return template.innerHTML;
  }

  function renderDetail(a) {
    state.selected = a;
    const categories = (a.source_categories || a.category || "Chưa phân loại")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    const links = a.sources || [];
    const body = (a.content || "").trim();
    const bodyHtml = (a.content_html || "").trim();
    const isTascoArticle = isTascoAnnouncement(links);
    const renderedBodyHtml = isTascoArticle
      ? scopeTascoLogos(bodyHtml)
      : bodyHtml;
    const hasRichPayload =
      Boolean(a.has_rich_payload) || richHtmlHasPayload(bodyHtml);
    const summary = (a.summary || "").trim();
    const hideDuplicateSummary = summaryRepeatsBody(
      summary,
      body || richHtmlText(bodyHtml),
    );
    const attachments = a.attachments || [];
    const hasDisplayableBody =
      Boolean(body) || hasRichPayload || attachments.length > 0;
    const quality = [];
    if (!a.published_at || dateIsUncertain(a))
      quality.push("Ngày đăng chưa được xác minh");
    // Some official notices consist only of a link/image/table. Don't flag them
    // as missing body when the extracted rich fragment is useful.
    if (!hasDisplayableBody)
      quality.push("Chưa trích xuất được nội dung hoặc liên kết hữu ích");
    if (
      a.title &&
      (a.title.includes("[CHƯA LẤY CHI TIẾT]") || /^Thong bao\b/i.test(a.title))
    )
      quality.push("Tiêu đề cần kiểm tra");
    $("#detail-panel").innerHTML = `<div class="detail-content">${renderDetailCloseButton()}
      <div class="detail-meta"><span class="source-chip">${esc(firstSource(a))}</span>${categories
        .slice(0, 3)
        .map((c) => `<span class="category-chip">${esc(c)}</span>`)
        .join("")}</div>
      <h2 class="detail-title">${esc(a.title)}</h2>
      <div class="detail-date-row"><span>▦ ${esc(fmtDate(a.published_at))}${dateIsUncertain(a) ? " · chưa xác minh" : ""}</span><span>·</span><span>${a.read_at ? "Đã đọc" : "Chưa đọc"}</span>${a.source_count > 1 ? `<span>· ${a.source_count} nguồn</span>` : ""}</div>
      <div class="detail-actions"><button class="button primary" id="toggle-read">${a.read_at ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}</button><button class="button favorite ${a.is_favorite ? "active" : ""}" id="toggle-favorite">${a.is_favorite ? "★ Đã lưu" : "☆ Lưu thông báo"}</button>${links[0] ? `<a class="button" target="_blank" rel="noopener noreferrer" href="${esc(links[0].source_url)}">Mở bài gốc ↗</a>` : ""}</div>
      ${summary && !hideDuplicateSummary ? `<div class="detail-summary">${esc(summary)}</div>` : ""}
      <div class="body-heading">Nội dung thông báo</div>
      ${bodyHtml && hasRichPayload ? `<div class="article-body rich-content${isTascoArticle ? " tasco-announcement" : ""}">${renderedBodyHtml}</div>` : body ? `<div class="article-body">${esc(body)}</div>` : `<div class="body-missing">${attachments.length ? "Trang nguồn không cung cấp phần thân bài đọc được; tệp liên quan được liệt kê bên dưới." : "Trang nguồn không cung cấp phần thân bài để nhúng. Mở bài gốc bên trên để xem liên kết, biểu mẫu hoặc nội dung bổ sung."}</div>`}
      ${attachments.length ? `<div class="body-heading">Tệp đính kèm</div><div class="attachment-list">${attachments.map((u) => `<a target="_blank" rel="noopener noreferrer" href="${esc(u)}">↳ ${esc(u.split("/").pop() || u)}</a>`).join("")}</div>` : ""}
      <div class="body-heading">Nguồn gốc</div><ul class="source-links">${links.map((l) => `<li><div class="source-link-name">${esc(l.source_name)} · ${esc(l.category || "")}</div>${l.source_url ? `<a class="source-link-url" href="${esc(l.source_url)}" target="_blank" rel="noopener noreferrer">${esc(l.source_url)}</a>` : '<span class="muted">Liên kết không hợp lệ</span>'}${l.last_detail_status ? `<div class="muted" style="margin:5px 0 0">Trích xuất lần cuối: ${esc(l.last_detail_status)}${l.last_detail_chars ? ` · ${l.last_detail_chars} ký tự` : ""}</div>` : '<div class="muted" style="margin:5px 0 0">Chưa có lịch sử thử tải chi tiết được lưu.</div>'}${l.last_detail_error ? `<div class="detail-fetch-error">Chi tiết: ${esc(l.last_detail_error)}</div>` : ""}</li>`).join("")}</ul>
      ${quality.length ? `<div class="quality-note">Cần lưu ý: ${quality.map(esc).join(" · ")}. Thông tin nguồn gốc được giữ để bạn đối chiếu với bài chính thức.</div>` : ""}
    </div>`;
    $("#close-detail").addEventListener("click", () => {
      state.selectedId = null;
      state.selected = null;
      renderEmptyDetail();
      document
        .querySelectorAll(".article-card.selected")
        .forEach((el) => el.classList.remove("selected"));
    });
    $("#toggle-read").addEventListener("click", () =>
      updateAction(a.id, "read", { read: !a.read_at }),
    );
    $("#toggle-favorite").addEventListener("click", () =>
      updateAction(a.id, "favorite", { favorite: !a.is_favorite }),
    );
  }
  async function loadDetail(id, markRead = true) {
    state.selectedId = id;
    document
      .querySelectorAll(".article-card")
      .forEach((el) =>
        el.classList.toggle("selected", Number(el.dataset.id) === id),
      );
    try {
      const a = await api("/api/articles/" + id);
      renderDetail(a);
      if (markRead && !a.read_at)
        await updateAction(id, "read", { read: true }, true);
    } catch (err) {
      toast("Không mở được bài: " + err.message);
    }
  }
  async function updateAction(id, action, payload, silent = false) {
    try {
      await api(`/api/articles/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!silent)
        toast(
          action === "read"
            ? payload.read
              ? "Đã đánh dấu đã đọc"
              : "Đã đánh dấu chưa đọc"
            : payload.favorite
              ? "Đã lưu thông báo"
              : "Đã bỏ lưu thông báo",
        );
      await loadStats();
      const card = document.querySelector(`.article-card[data-id="${id}"]`);
      if (action === "read" && card)
        card.classList.toggle("unread", !payload.read);
      if (state.selectedId === id) await loadDetail(id, false);
    } catch (err) {
      toast("Không lưu được: " + err.message);
    }
  }
  function syncNav() {
    document
      .querySelectorAll(".nav-item")
      .forEach((el) =>
        el.classList.toggle("active", el.dataset.mode === state.mode),
      );
    document
      .querySelectorAll(".source-shortcut")
      .forEach((el) =>
        el.classList.toggle("active", el.dataset.source === state.source),
      );
  }
  function bindEvents() {
    document.querySelectorAll(".nav-item").forEach((el) =>
      el.addEventListener("click", () => {
        state.mode = el.dataset.mode;
        state.page = 1;
        syncNav();
        loadList(true);
      }),
    );
    $("#source-filter").addEventListener("change", (e) => {
      state.source = e.target.value;
      state.page = 1;
      syncNav();
      loadList();
    });
    $("#academic-year-filter").addEventListener("change", async (e) => {
      state.academicYear = e.target.value;
      state.page = 1;
      try {
        await loadStats();
        await loadList();
      } catch (err) {
        toast("Không lọc được năm học: " + err.message);
      }
    });
    $("#sort-category").addEventListener("change", (e) => {
      state.category = e.target.value;
      state.page = 1;
      loadList();
    });
    $("#search-input").addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.q = e.target.value.trim();
        state.page = 1;
        loadList();
      }, 240);
    });
    $("#feed-list").addEventListener("click", (e) => {
      const card = e.target.closest(".article-card");
      if (card) loadDetail(Number(card.dataset.id));
    });
    $("#feed-list").addEventListener("keydown", (e) => {
      if (
        (e.key === "Enter" || e.key === " ") &&
        e.target.classList.contains("article-card")
      ) {
        e.preventDefault();
        loadDetail(Number(e.target.dataset.id));
      }
    });
    $("#source-list").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-source]");
      if (!btn) return;
      state.source =
        state.source === btn.dataset.source ? "" : btn.dataset.source;
      $("#source-filter").value = state.source;
      state.page = 1;
      syncNav();
      loadList();
    });
    $("#prev-page").addEventListener("click", () => {
      if (state.page > 1) {
        state.page--;
        loadList();
      }
    });
    $("#next-page").addEventListener("click", () => {
      if (state.page < state.pages) {
        state.page++;
        loadList();
      }
    });
    $("#refresh-btn").addEventListener("click", async () => {
      try {
        await loadStats();
        await loadList();
        const currentCheck = await api("/api/website-check");
        if (currentCheck.status === "running") return;
        const check = await api("/api/website-check", { method: "POST" }).catch(
          (err) => {
            if (err.message.includes("Đang có lượt kiểm tra")) return null;
            throw err;
          },
        );
        if (check) {
          websiteCheckLastStatus = "running";
          renderWebsiteCheck(check);
          pollWebsiteCheck();
        }
      } catch (e) {
        toast("Không tải lại được: " + e.message);
      }
    });
    $("#mark-all-read").addEventListener("click", async () => {
      const unread = Number(state.stats?.unread || 0);
      if (!unread) {
        toast("Không còn thông báo chưa đọc");
        return;
      }
      const scope = state.academicYear
        ? `trong năm học ${state.academicYear.replace("-", "–")}`
        : "từ trước đến nay trong CSDL";
      if (
        !window.confirm(
          `Đánh dấu ${unread} thông báo chưa đọc ${scope} là đã đọc?`,
        )
      )
        return;
      try {
        const result = await api("/api/read-all", {
          method: "POST",
          body: JSON.stringify({ academic_year: state.academicYear }),
        });
        toast(
          `Đã đánh dấu ${Number(result.updated || 0).toLocaleString("vi-VN")} thông báo là đã đọc`,
        );
        await loadStats();
        if (state.selectedId !== null)
          await loadDetail(state.selectedId, false);
      } catch (err) {
        toast("Không thể đánh dấu tất cả đã đọc: " + err.message);
      }
    });
  }
  async function init() {
    bindEvents();
    try {
      await loadStats();
      await loadList();
      await pollVersion();
      await pollWebsiteCheck();
      startPolling();
    } catch (err) {
      setStatus("Không kết nối được CSDL", false);
      $("#feed-list").innerHTML =
        `<div class="empty-state">${esc(err.message)}</div>`;
    }
  }
  init();
})();
