/**
 * Bot-Obsidian Telegram Mini App — Dashboard Controller
 *
 * Connects to FastAPI backend via WebSocket for real-time updates.
 * Falls back to REST polling if WS unavailable.
 */

(function () {
    "use strict";

    // ---- Telegram WebApp init ----
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();
    }

    // ---- Config ----
    const WS_URL = `ws://${location.host}/ws`;
    const API_URL = `${location.origin}/api`;
    const RECONNECT_DELAY = 3000;
    const POLL_INTERVAL = 5000;

    // ---- State ----
    let ws = null;
    let wsConnected = false;
    let pollTimer = null;
    let lastSnapshot = null;

    // ---- DOM refs ----
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ---- Tab switching ----
    $$(".tab").forEach((btn) => {
        btn.addEventListener("click", () => {
            $$(".tab").forEach((t) => t.classList.remove("active"));
            $$(".tab-content").forEach((c) => c.classList.remove("active"));
            btn.classList.add("active");
            $(`#tab-${btn.dataset.tab}`).classList.add("active");
        });
    });

    // ---- WebSocket ----

    function connectWS() {
        if (ws && ws.readyState <= 1) return;

        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            wsConnected = true;
            setStatus("live", "Connected");
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        };

        ws.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                if (data.type === "snapshot") {
                    lastSnapshot = data;
                    render(data);
                }
            } catch (e) {
                console.error("WS parse error:", e);
            }
        };

        ws.onclose = () => {
            wsConnected = false;
            setStatus("error", "Disconnected");
            startPolling();
            setTimeout(connectWS, RECONNECT_DELAY);
        };

        ws.onerror = () => {
            ws.close();
        };

        // Keepalive ping
        setInterval(() => {
            if (ws && ws.readyState === 1) {
                ws.send(JSON.stringify({ type: "ping" }));
            }
        }, 30000);
    }

    // ---- REST fallback ----

    function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(async () => {
            if (wsConnected) return;
            try {
                const res = await fetch(`${API_URL}/status`);
                const data = await res.json();
                lastSnapshot = data;
                render(data);
                setStatus("live", "Polling");
            } catch {
                setStatus("error", "Offline");
            }
        }, POLL_INTERVAL);
    }

    // ---- Rendering ----

    function render(snap) {
        renderPnL(snap.pnl);
        renderPositionsSummary(snap.positions);
        renderPositionsDetail(snap.positions);
        renderAlerts(snap.alerts);
        renderMarket(snap.market);
        renderSignals(snap.signals);
        renderStatus(snap.status, snap.settings);
        syncSettings(snap.settings);
    }

    function renderPnL(pnl) {
        if (!pnl) return;

        const equityEl = $("#equity");
        equityEl.textContent = formatUSD(pnl.total_equity);

        $("#equity-sub").textContent = `Peak: ${formatUSD(pnl.peak_equity)}`;

        const pnlEl = $("#daily-pnl");
        pnlEl.textContent = formatUSD(pnl.daily_pnl, true);
        pnlEl.className = "card-value " + (pnl.daily_pnl >= 0 ? "positive" : "negative");

        const pnlPct =
            pnl.total_equity > 0
                ? ((pnl.daily_pnl / pnl.total_equity) * 100).toFixed(2)
                : "0.00";
        const pnlPctEl = $("#pnl-pct");
        pnlPctEl.textContent = `${pnl.daily_pnl >= 0 ? "+" : ""}${pnlPct}%`;
        pnlPctEl.className = "card-sub " + (pnl.daily_pnl >= 0 ? "text-green" : "text-red");

        const ddEl = $("#drawdown");
        ddEl.textContent = `${pnl.drawdown_pct.toFixed(2)}%`;
        ddEl.className =
            "card-value " + (pnl.drawdown_pct > 10 ? "negative" : pnl.drawdown_pct > 5 ? "text-yellow" : "");

        const ddBar = $("#dd-bar");
        const ddWidth = Math.min(pnl.drawdown_pct / 15 * 100, 100);
        ddBar.style.width = `${ddWidth}%`;
        ddBar.className = "progress-bar" + (pnl.drawdown_pct > 10 ? " danger" : pnl.drawdown_pct > 5 ? " warning" : "");

        $("#pos-count").textContent = pnl.positions_count;
    }

    function renderPositionsSummary(positions) {
        const container = $("#positions-summary");
        if (!positions || positions.length === 0) {
            container.innerHTML = '<div class="empty-state">No open positions</div>';
            return;
        }
        container.innerHTML = positions.map((p) => positionCardHTML(p, false)).join("");
    }

    function renderPositionsDetail(positions) {
        const container = $("#positions-detail");
        if (!positions || positions.length === 0) {
            container.innerHTML = '<div class="empty-state">No open positions</div>';
            return;
        }
        container.innerHTML = positions.map((p) => positionCardHTML(p, true)).join("");
    }

    function positionCardHTML(p, detailed) {
        const dir = p.direction.toLowerCase();
        const pnlClass = p.unrealized_pnl >= 0 ? "text-green" : "text-red";
        const pnlSign = p.unrealized_pnl >= 0 ? "+" : "";

        let detailRows = "";
        if (detailed) {
            detailRows = `
                <div class="pos-field"><span class="pos-field-label">Qty</span><span class="pos-field-value">${p.qty.toFixed(6)}</span></div>
                <div class="pos-field"><span class="pos-field-label">ATR</span><span class="pos-field-value">${p.atr.toFixed(2)}</span></div>
                <div class="pos-field"><span class="pos-field-label">Peak</span><span class="pos-field-value">${formatPrice(p.peak)}</span></div>
                <div class="pos-field"><span class="pos-field-label">Opened</span><span class="pos-field-value">${formatTime(p.opened_at)}</span></div>
            `;
        }

        return `
            <div class="position-card ${dir}">
                <div class="pos-header">
                    <span class="pos-symbol">${p.symbol}</span>
                    <span class="pos-direction ${dir}">${p.direction}</span>
                </div>
                <div class="pos-grid">
                    <div class="pos-field"><span class="pos-field-label">Entry</span><span class="pos-field-value">${formatPrice(p.entry_price)}</span></div>
                    <div class="pos-field"><span class="pos-field-label">SL</span><span class="pos-field-value">${formatPrice(p.sl)}</span></div>
                    ${detailRows}
                </div>
                <div class="pos-pnl">
                    <span class="pos-pnl-value ${pnlClass}">${pnlSign}${formatUSD(p.unrealized_pnl)}</span>
                    <span class="pos-pnl-pct ${pnlClass}">${pnlSign}${p.pnl_pct.toFixed(2)}%</span>
                </div>
            </div>
        `;
    }

    function renderAlerts(alerts) {
        const container = $("#alerts-list");
        if (!alerts || alerts.length === 0) {
            container.innerHTML = '<div class="empty-state">No alerts yet</div>';
            return;
        }
        const sorted = [...alerts].reverse();
        container.innerHTML = sorted
            .slice(0, 20)
            .map((a) => {
                const level = (a.level || "info").toLowerCase();
                const dotClass = level === "error" ? "error" : level === "warn" ? "warn" : level === "trade" ? "trade" : "info";
                return `
                <div class="alert-item">
                    <div class="alert-dot ${dotClass}"></div>
                    <div class="alert-content">
                        <div class="alert-time">${formatTimestamp(a.timestamp)} &middot; ${a.symbol}</div>
                        <div class="alert-msg">${escapeHTML(a.message)}</div>
                    </div>
                </div>
            `;
            })
            .join("");
    }

    function renderMarket(market) {
        const container = $("#market-grid");
        if (!market || Object.keys(market).length === 0) {
            const defaultSymbols = ["BTC", "ETH", "SOL", "ADA"];
            container.innerHTML = defaultSymbols
                .map(
                    (s) => `
                <div class="market-card">
                    <div class="market-symbol">${s}</div>
                    <div class="market-price" style="color:var(--text-secondary)">---</div>
                    <div class="market-change">Awaiting data</div>
                </div>
            `
                )
                .join("");
            return;
        }

        container.innerHTML = Object.entries(market)
            .map(([sym, d]) => {
                const change = d.change_24h || 0;
                const changeClass = change >= 0 ? "up" : "down";
                const changeSign = change >= 0 ? "+" : "";
                return `
                <div class="market-card">
                    <div class="market-symbol">${sym}</div>
                    <div class="market-price">${formatPrice(d.price)}</div>
                    <div class="market-change ${changeClass}">${changeSign}${change.toFixed(2)}%</div>
                    <div class="market-row"><span>OI Chg 1h</span><span>${(d.oi_change_1h || 0).toFixed(2)}%</span></div>
                    <div class="market-row"><span>Funding</span><span>${((d.funding_rate || 0) * 100).toFixed(4)}%</span></div>
                    <div class="market-row"><span>Regime</span><span>${d.regime || "-"}</span></div>
                </div>
            `;
            })
            .join("");
    }

    function renderSignals(signals) {
        const container = $("#signals-list");
        if (!signals || signals.length === 0) {
            container.innerHTML = '<div class="empty-state">No signals yet</div>';
            return;
        }
        const sorted = [...signals].reverse();
        container.innerHTML = sorted
            .map((s) => {
                const dir = (s.direction || "").toLowerCase();
                const strength = Math.round((s.strength || 0) * 100);
                const passedTags = (s.filters_passed || [])
                    .map((f) => `<span class="filter-tag pass">${f}</span>`)
                    .join("");
                const rejectedTags = (s.filters_rejected || [])
                    .map((f) => `<span class="filter-tag fail">${f}</span>`)
                    .join("");
                return `
                <div class="signal-item">
                    <div class="signal-header">
                        <span class="signal-pair">${s.symbol || ""}</span>
                        <span class="signal-dir ${dir}">${(s.direction || "").toUpperCase()}</span>
                    </div>
                    <div class="signal-strength"><div class="signal-strength-bar" style="width:${strength}%"></div></div>
                    <div class="signal-meta">
                        <span>Strength: ${strength}%</span>
                        <span>${formatTimestamp(s.timestamp)}</span>
                    </div>
                    <div class="signal-filters">${passedTags}${rejectedTags}</div>
                </div>
            `;
            })
            .join("");
    }

    function renderStatus(status, settings) {
        if (!status) return;

        const badge = $("#mode-badge");
        badge.textContent = status.mode;
        if (status.mode === "LIVE") {
            badge.classList.add("live-mode");
        } else {
            badge.classList.remove("live-mode");
        }

        $("#sys-uptime").textContent = formatDuration(status.uptime_seconds);
        $("#sys-ws").textContent = wsConnected ? `Connected (${status.ws_clients} clients)` : "Polling";
        $("#sys-ws").style.color = wsConnected ? "var(--green)" : "var(--yellow)";
        $("#sys-cycle").textContent = status.last_cycle || "-";

        if (settings) {
            $("#pos-max").textContent = `/ ${settings.max_open_positions} max`;
        }
    }

    // ---- Settings ----

    let settingsSynced = false;

    function syncSettings(settings) {
        if (!settings || settingsSynced) return;
        settingsSynced = true;

        setSlider("set-margin", "val-margin", settings.margin_pct * 100, (v) => `${v}%`);
        setSlider("set-leverage", "val-leverage", settings.leverage, (v) => `${v}x`);
        setSlider("set-trail", "val-trail", settings.trail_atr, (v) => v.toFixed(1));
        setSlider("set-maxloss", "val-maxloss", settings.max_daily_loss_pct * 100, (v) => `${v}%`);
        setSlider("set-maxpos", "val-maxpos", settings.max_open_positions, (v) => v);
        setSlider("set-confidence", "val-confidence", settings.min_confidence, (v) => v.toFixed(1));

        const paperEl = $("#set-paper");
        paperEl.checked = settings.paper_trading;
    }

    function setSlider(inputId, valueId, value, formatter) {
        const input = $(`#${inputId}`);
        const display = $(`#${valueId}`);
        input.value = value;
        display.textContent = formatter(Number(value));
        input.oninput = () => {
            display.textContent = formatter(Number(input.value));
            settingsSynced = true; // Allow re-sync after manual change
        };
    }

    $("#btn-save-settings").addEventListener("click", async () => {
        const updates = {
            margin_pct: Number($("#set-margin").value) / 100,
            leverage: Number($("#set-leverage").value),
            trail_atr: Number($("#set-trail").value),
            max_daily_loss_pct: Number($("#set-maxloss").value) / 100,
            max_open_positions: Number($("#set-maxpos").value),
            min_confidence: Number($("#set-confidence").value),
            paper_trading: $("#set-paper").checked,
        };

        try {
            const res = await fetch(`${API_URL}/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(updates),
            });
            if (res.ok) {
                const btn = $("#btn-save-settings");
                btn.textContent = "Saved!";
                btn.classList.add("saved");
                setTimeout(() => {
                    btn.textContent = "Save Settings";
                    btn.classList.remove("saved");
                }, 2000);
                settingsSynced = false;
            }
        } catch (e) {
            console.error("Save settings error:", e);
        }
    });

    // ---- Helpers ----

    function setStatus(type, text) {
        const dot = $(".status-dot");
        const label = $(".status-text");
        dot.className = "status-dot " + type;
        label.textContent = text;
    }

    function formatUSD(val, showSign) {
        if (val == null) return "$0.00";
        const abs = Math.abs(val);
        let str;
        if (abs >= 1_000_000) str = `$${(abs / 1_000_000).toFixed(2)}M`;
        else if (abs >= 1_000) str = `$${abs.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}`;
        else str = `$${abs.toFixed(2)}`;
        if (showSign && val > 0) str = "+" + str;
        if (val < 0) str = "-" + str;
        return str;
    }

    function formatPrice(val) {
        if (val == null || val === 0) return "---";
        if (val >= 1000) return val.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        if (val >= 1) return val.toFixed(4);
        return val.toFixed(6);
    }

    function formatTimestamp(ts) {
        if (!ts) return "";
        const d = typeof ts === "string" ? new Date(ts) : new Date(ts * 1000);
        if (isNaN(d.getTime())) return String(ts).slice(0, 19);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function formatTime(str) {
        if (!str) return "-";
        try {
            const d = new Date(str);
            return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
        } catch {
            return str;
        }
    }

    function formatDuration(sec) {
        if (!sec) return "-";
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

    function escapeHTML(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ---- Init ----

    setStatus("", "Connecting...");
    connectWS();

    // Fallback: if WS fails to connect in 3s, start polling
    setTimeout(() => {
        if (!wsConnected) startPolling();
    }, 3000);
})();
