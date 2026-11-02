"""
web_dashboard.py - Parental Control Web Dashboard
-------------------------------------------------
Independent web interface for parents to monitor and manage child screen time.
Reads and writes directly to the shared SQLite database (study_monitor.db).

Capabilities:
1. Real-time child status (active window, running app, remaining allowed time).
2. Live application tracking table (time spent today per process).
3. Parental enforcement rules manager (add, update, delete time limits and blocklists).
4. Remote actions: Instant lockdown, bonus time accrual (+15m, +30m, +60m), and process termination.
5. Dual runtime architecture: Runs natively via Flask if available, or seamlessly via
   Python's built-in ThreadingHTTPServer with zero external dependencies.
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

import db_manager
import enforcement

PORT = 8000
HOST = "0.0.0.0"

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demon Parental Control & Study Monitor</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%234f46e5'/%3E%3Ctext y='68' x='50' font-size='60' text-anchor='middle'%3E%F0%9F%9B%A1%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #090d16; color: #f1f5f9; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .glass { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .glass-card { background: rgba(17, 24, 39, 0.6); border: 1px solid rgba(255, 255, 255, 0.06); }
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

        <!-- Top Header Navigation -->
        <header class="glass p-5 rounded-2xl flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-2xl">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-2xl">
                    🛡️
                </div>
                <div>
                    <h1 class="text-xl md:text-2xl font-black text-white tracking-tight flex items-center gap-2">
                        Demon <span class="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 font-semibold uppercase">Parental View</span>
                    </h1>
                    <p class="text-xs text-slate-400">Autonomous Background Process Monitoring & Rules Enforcement</p>
                </div>
            </div>

            <!-- Quick Parental Overrides -->
            <div class="flex flex-wrap items-center gap-2">
                <button onclick="adjustTime(900)" class="px-3.5 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-xs font-bold transition">
                    +15m Bonus
                </button>
                <button onclick="adjustTime(1800)" class="px-3.5 py-2 rounded-xl bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-300 text-xs font-bold transition">
                    +30m Bonus
                </button>
                <button onclick="adjustTime(3600)" class="px-3.5 py-2 rounded-xl bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/40 text-blue-300 text-xs font-bold transition">
                    +1h Bonus
                </button>
                <button id="lockdown-btn" onclick="toggleParentalLock()" class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-rose-950/50">
                    <span id="lockdown-icon">🔒</span> <span id="lockdown-text">Instant Lockdown</span>
                </button>
            </div>
        </header>

        <!-- Status Overview Hero Grid -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            
            <!-- Card 1: Remaining Allowed Time -->
            <div class="glass-card p-5 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Remaining Screen Time</span>
                <div class="my-3">
                    <span id="balance-timer" class="text-4xl font-extrabold mono text-white tracking-tight">00:00:00</span>
                </div>
                <div class="flex items-center justify-between text-xs text-slate-400">
                    <span>Daily Limit: <strong id="daily-limit-text" class="text-slate-300">120m</strong></span>
                    <button onclick="promptSetBalance()" class="text-indigo-400 hover:text-indigo-300 underline font-semibold">Set Time</button>
                </div>
            </div>

            <!-- Card 2: Current Status -->
            <div class="glass-card p-5 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Child PC Status</span>
                <div class="my-3 flex items-center gap-3">
                    <div id="status-pulse" class="w-4 h-4 rounded-full bg-emerald-500 animate-pulse"></div>
                    <span id="status-label" class="text-xl font-bold text-emerald-400">ACTIVE & ALLOWED</span>
                </div>
                <span id="lock-subtext" class="text-xs text-slate-400">Rules active and enforcing</span>
            </div>

            <!-- Card 3: Active Application -->
            <div class="glass-card p-5 rounded-2xl flex flex-col justify-between">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Foreground Application</span>
                    <span id="active-category" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-bold">General</span>
                </div>
                <div class="my-2">
                    <div id="active-process" class="text-lg font-bold text-white mono truncate">None Detected</div>
                    <div id="active-window" class="text-xs text-slate-400 truncate mt-0.5">Desktop Idle</div>
                </div>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-slate-400">Live Window</span>
                    <button id="kill-active-btn" onclick="killCurrentProcess()" class="text-[11px] px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500/40 text-rose-300 font-bold border border-rose-500/30 transition">
                        Terminate App
                    </button>
                </div>
            </div>

            <!-- Card 4: Web Filter -->
            <div class="glass-card p-5 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Distraction Filter</span>
                <div class="my-3 flex items-center justify-between">
                    <div>
                        <span id="web-filter-label" class="text-lg font-bold text-white">Hosts Blocker</span>
                        <p class="text-xs text-slate-400">YouTube, TikTok, Netflix</p>
                    </div>
                    <span id="filter-badge" class="px-2.5 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-300">Inactive</span>
                </div>
                <button onclick="toggleWebFilter()" class="text-xs text-indigo-400 hover:text-indigo-300 font-semibold text-left">
                    Toggle Domain Blocker
                </button>
            </div>
        </div>

        <!-- Main Workspace: Rules & Process Management -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

            <!-- Left 2 Cols: Monitored Processes Table -->
            <div class="lg:col-span-2 glass p-6 rounded-2xl space-y-4 shadow-xl">
                <div class="flex items-center justify-between">
                    <div>
                        <h2 class="text-lg font-bold text-white tracking-tight">Tracked Applications Today</h2>
                        <p class="text-xs text-slate-400">Live screen time recorded by headless background service</p>
                    </div>
                    <button onclick="fetchData()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-300 transition">
                        Refresh
                    </button>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-400 uppercase font-semibold">
                                <th class="py-3 px-3">Process</th>
                                <th class="py-3 px-3">Category</th>
                                <th class="py-3 px-3">Time Today</th>
                                <th class="py-3 px-3">Total Time</th>
                                <th class="py-3 px-3">Rule Status</th>
                                <th class="py-3 px-3 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody id="processes-table-body" class="divide-y divide-slate-800/60">
                            <tr><td colspan="6" class="py-6 text-center text-slate-500">Loading tracked processes...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Right Col: Enforcement Rules & Limits Manager -->
            <div class="glass p-6 rounded-2xl space-y-5 shadow-xl">
                <div class="flex items-center justify-between">
                    <h2 class="text-lg font-bold text-white tracking-tight">Enforcement Rules</h2>
                    <span id="rules-count-badge" class="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-bold">0 Active</span>
                </div>

                <!-- Add New Rule Form -->
                <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
                    <span class="text-xs font-bold text-slate-300 block">Add or Update Restriction</span>
                    <div class="space-y-2">
                        <input id="rule-proc" type="text" placeholder="e.g. discord.exe, roblox.exe" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 mono">
                        <div class="grid grid-cols-2 gap-2">
                            <input id="rule-limit" type="number" min="0" placeholder="Limit (min, 0=block)" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500">
                            <select id="rule-cat" class="w-full px-2 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500">
                                <option value="Gaming">Gaming</option>
                                <option value="Social & Chat">Social & Chat</option>
                                <option value="Entertainment">Entertainment</option>
                                <option value="General">General</option>
                            </select>
                        </div>
                        <button onclick="submitNewRule()" class="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition">
                            Save Rule
                        </button>
                    </div>
                </div>

                <!-- Rules List -->
                <div id="rules-list-container" class="space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
                    <div class="text-center text-xs text-slate-500 py-4">Loading rules...</div>
                </div>
            </div>
        </div>

        <!-- Activity & Intervention Audit Ledger -->
        <div class="glass p-6 rounded-2xl space-y-3 shadow-xl">
            <h2 class="text-md font-bold text-white tracking-tight">Recent Activity & Enforcement Ledger</h2>
            <div id="audit-log-container" class="text-xs space-y-1.5 mono max-h-48 overflow-y-auto">
                <div class="text-slate-500">Listening to database transactions...</div>
            </div>
        </div>

    </div>

    <!-- Client-Side Real-time Dashboard Logic -->
    <script>
        let currentStatus = {};

        function formatSeconds(sec) {
            sec = Math.max(0, Math.floor(sec));
            const h = Math.floor(sec / 3600);
            const m = Math.floor((sec % 3600) / 60);
            const s = sec % 60;
            return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }

        async function fetchData() {
            try {
                // 1. Fetch system status
                const resStatus = await fetch('/api/status');
                const statusData = await resStatus.json();
                currentStatus = statusData;
                renderStatus(statusData);

                // 2. Fetch tracked processes
                const resProc = await fetch('/api/processes');
                const procData = await resProc.json();
                renderProcesses(procData);

                // 3. Fetch enforcement rules
                const resRules = await fetch('/api/rules');
                const rulesData = await resRules.json();
                renderRules(rulesData);

                // 4. Fetch logs
                const resLogs = await fetch('/api/logs');
                const logsData = await resLogs.json();
                renderLogs(logsData);
            } catch (err) {
                console.warn("Dashboard sync error:", err);
            }
        }

        function renderStatus(data) {
            document.getElementById('balance-timer').textContent = formatSeconds(data.balance);
            document.getElementById('daily-limit-text').textContent = `${data.daily_limit_minutes || 120}m`;

            const activeProc = data.current_process || "Desktop Idle";
            const activeWin = data.current_window || "No active foreground window";
            document.getElementById('active-process').textContent = activeProc;
            document.getElementById('active-window').textContent = activeWin;

            const isLocked = data.is_blocked === 1 || data.balance <= 0;
            const statusLabel = document.getElementById('status-label');
            const statusPulse = document.getElementById('status-pulse');
            const lockBtn = document.getElementById('lockdown-btn');
            const lockText = document.getElementById('lockdown-text');
            const lockIcon = document.getElementById('lockdown-icon');
            const lockSubtext = document.getElementById('lock-subtext');

            if (isLocked) {
                statusLabel.textContent = "LOCKDOWN ACTIVE";
                statusLabel.className = "text-xl font-bold text-rose-500";
                statusPulse.className = "w-4 h-4 rounded-full bg-rose-500 animate-ping";
                lockText.textContent = "Unlock Child PC";
                lockIcon.textContent = "🔓";
                lockBtn.className = "px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-emerald-950/50";
                lockSubtext.textContent = data.balance <= 0 ? "Allowed time exhausted (0s remaining)" : "Manually locked by parent";
            } else {
                statusLabel.textContent = "ACTIVE & ALLOWED";
                statusLabel.className = "text-xl font-bold text-emerald-400";
                statusPulse.className = "w-4 h-4 rounded-full bg-emerald-500 animate-pulse";
                lockText.textContent = "Instant Lockdown";
                lockIcon.textContent = "🔒";
                lockBtn.className = "px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-rose-950/50";
                lockSubtext.textContent = "All standard parental limits enforcing";
            }

            const filterBadge = document.getElementById('filter-badge');
            if (data.hosts_blocked) {
                filterBadge.textContent = "BLOCKED";
                filterBadge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40";
            } else {
                filterBadge.textContent = "UNBLOCKED";
                filterBadge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-400";
            }
        }

        function renderProcesses(processes) {
            const tbody = document.getElementById('processes-table-body');
            if (!processes || processes.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-500">No applications recorded yet today. Background tracker is active.</td></tr>`;
                return;
            }

            tbody.innerHTML = processes.map(p => {
                const todayMins = Math.round((p.today_time_seconds / 60) * 10) / 10;
                const totalMins = Math.round((p.total_time_seconds / 60) * 10) / 10;
                const isBlocked = p.rule_is_blocked === 1;
                const hasLimit = p.time_limit_minutes > 0;

                let statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 font-semibold">Allowed</span>`;
                if (isBlocked) {
                    statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-rose-500/20 text-rose-400 border border-rose-500/40 font-bold">Blocked</span>`;
                } else if (hasLimit) {
                    const over = todayMins >= p.time_limit_minutes;
                    statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] ${over ? 'bg-rose-500/20 text-rose-400' : 'bg-amber-500/20 text-amber-300'} font-bold">${todayMins}/${p.time_limit_minutes}m</span>`;
                }

                return `
                    <tr class="hover:bg-slate-900/40 transition">
                        <td class="py-3 px-3 font-semibold text-white mono">${escapeHtml(p.process_name)}</td>
                        <td class="py-3 px-3 text-slate-400">${escapeHtml(p.category || 'General')}</td>
                        <td class="py-3 px-3 font-bold text-indigo-300 mono">${todayMins}m</td>
                        <td class="py-3 px-3 text-slate-400 mono">${totalMins}m</td>
                        <td class="py-3 px-3">${statusBadge}</td>
                        <td class="py-3 px-3 text-right space-x-1.5">
                            <button onclick="quickBlock('${escapeHtml(p.process_name)}', ${isBlocked ? 0 : 1})" class="px-2 py-1 rounded ${isBlocked ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'} font-bold transition text-[11px]">
                                ${isBlocked ? 'Unblock' : 'Block'}
                            </button>
                            <button onclick="quickKill('${escapeHtml(p.process_name)}')" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold transition text-[11px]">
                                Kill
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        function renderRules(rules) {
            const container = document.getElementById('rules-list-container');
            const countBadge = document.getElementById('rules-count-badge');
            countBadge.textContent = `${rules.length} Rules`;

            if (!rules || rules.length === 0) {
                container.innerHTML = `<div class="text-center text-xs text-slate-500 py-4">No rules created yet.</div>`;
                return;
            }

            container.innerHTML = rules.map(r => `
                <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80 flex items-center justify-between">
                    <div>
                        <div class="font-bold text-white mono text-xs">${escapeHtml(r.process_name)}</div>
                        <div class="text-[11px] text-slate-400 mt-0.5">
                            ${r.is_blocked ? '<span class="text-rose-400 font-bold">Permanently Blocked</span>' : `Daily Limit: <strong class="text-slate-300">${r.time_limit_minutes}m</strong>`}
                            · ${escapeHtml(r.category)}
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="quickBlock('${escapeHtml(r.process_name)}', ${r.is_blocked ? 0 : 1})" class="text-xs px-2 py-1 rounded ${r.is_blocked ? 'bg-emerald-600/30 text-emerald-300' : 'bg-rose-600/30 text-rose-300'} font-bold">
                            ${r.is_blocked ? 'Allow' : 'Block'}
                        </button>
                        <button onclick="deleteRule('${escapeHtml(r.process_name)}')" class="text-slate-500 hover:text-rose-400 p-1 text-sm font-bold">
                            ✕
                        </button>
                    </div>
                </div>
            `).join('');
        }

        function renderLogs(logs) {
            const container = document.getElementById('audit-log-container');
            if (!logs || logs.length === 0) {
                container.innerHTML = `<div class="text-slate-500">No logs recorded yet.</div>`;
                return;
            }

            container.innerHTML = logs.map(l => {
                const sign = l.delta > 0 ? `+${l.delta}s` : `${l.delta}s`;
                const deltaColor = l.delta > 0 ? 'text-emerald-400' : (l.delta < 0 ? 'text-rose-400' : 'text-slate-400');
                return `
                    <div class="flex items-center justify-between py-1 border-b border-slate-900/60">
                        <span class="text-slate-400 text-[11px]">${l.timestamp.split('T')[1].split('.')[0]}</span>
                        <span class="text-slate-300 truncate max-w-md">${escapeHtml(l.reason || 'General cycle')}</span>
                        <span class="${deltaColor} font-bold">${sign}</span>
                        <span class="text-slate-500 text-[10px]">Bal: ${l.balance_after}s</span>
                    </div>
                `;
            }).join('');
        }

        // ==========================================
        // ACTION HANDLERS
        // ==========================================
        async function adjustTime(deltaSeconds) {
            await fetch('/api/adjust-time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delta: deltaSeconds })
            });
            fetchData();
        }

        async function promptSetBalance() {
            const min = prompt("Set remaining allowed time in MINUTES for child:", "60");
            if (min !== null && !isNaN(parseInt(min))) {
                const sec = parseInt(min) * 60;
                await fetch('/api/set-time', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ balance: sec })
                });
                fetchData();
            }
        }

        async function toggleParentalLock() {
            const isCurrentlyLocked = currentStatus.is_blocked === 1 || currentStatus.balance <= 0;
            await fetch('/api/toggle-lock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ locked: !isCurrentlyLocked })
            });
            fetchData();
        }

        async function toggleWebFilter() {
            await fetch('/api/toggle-web-filter', { method: 'POST' });
            fetchData();
        }

        async function quickBlock(processName, blockState) {
            await fetch('/api/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    process_name: processName,
                    is_blocked: blockState,
                    time_limit_minutes: blockState ? 0 : 60
                })
            });
            fetchData();
        }

        async function quickKill(processName) {
            if (confirm(`Immediately terminate all running instances of '${processName}'?`)) {
                await fetch('/api/kill-process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ process_name: processName })
                });
                fetchData();
            }
        }

        async function killCurrentProcess() {
            const proc = currentStatus.current_process;
            if (proc) {
                quickKill(proc);
            } else {
                alert("No active process detected.");
            }
        }

        async function deleteRule(processName) {
            if (confirm(`Remove restriction rule for '${processName}'?`)) {
                await fetch('/api/rules/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ process_name: processName })
                });
                fetchData();
            }
        }

        async function submitNewRule() {
            const proc = document.getElementById('rule-proc').value.trim();
            const limitVal = document.getElementById('rule-limit').value.trim();
            const cat = document.getElementById('rule-cat').value;

            if (!proc) {
                alert("Please enter a process executable name (e.g. discord.exe).");
                return;
            }

            const limitMin = limitVal === "" ? 60 : parseInt(limitVal);
            const isBlocked = limitMin === 0 ? 1 : 0;

            await fetch('/api/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    process_name: proc,
                    time_limit_minutes: limitMin,
                    is_blocked: isBlocked,
                    category: cat,
                    action: 'terminate'
                })
            });

            document.getElementById('rule-proc').value = '';
            document.getElementById('rule-limit').value = '';
            fetchData();
        }

        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/[&<>"']/g, function(m) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
            });
        }

        setInterval(fetchData, 1500);
        fetchData();
    </script>
</body>
</html>
"""


# ==============================================================================
# FLASK & THREADING HTTP SERVER ENGINE
# ==============================================================================

def get_system_status_payload() -> Dict[str, Any]:
    """Compiles complete parental control telemetry payload."""
    state = db_manager.get_child_state()
    return {
        "balance": state.get("current_balance", 0),
        "daily_limit_minutes": state.get("daily_limit_minutes", 120),
        "is_blocked": state.get("is_blocked", 0),
        "current_process": state.get("current_process", ""),
        "current_window": state.get("current_window", ""),
        "last_updated": state.get("last_updated", ""),
        "hosts_blocked": enforcement.is_distraction_blocked(),
        "is_admin": enforcement.is_admin()
    }


# Attempt to create Flask App if installed, with seamless fallback
try:
    from flask import Flask, jsonify, request, Response
    flask_available = True
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def flask_index():
        return Response(DASHBOARD_HTML, mimetype="text/html")

    @app.route("/api/status", methods=["GET"])
    def flask_status():
        return jsonify(get_system_status_payload())

    @app.route("/api/processes", methods=["GET"])
    def flask_processes():
        return jsonify(db_manager.get_tracked_processes(limit=100))

    @app.route("/api/rules", methods=["GET"])
    def flask_get_rules():
        return jsonify(db_manager.get_enforcement_rules())

    @app.route("/api/rules", methods=["POST"])
    def flask_set_rule():
        data = request.get_json() or {}
        p_name = data.get("process_name", "")
        if p_name:
            db_manager.set_enforcement_rule(
                process_name=p_name,
                display_name=data.get("display_name"),
                time_limit_minutes=int(data.get("time_limit_minutes", 60)),
                is_blocked=int(data.get("is_blocked", 0)),
                action=data.get("action", "terminate"),
                category=data.get("category", "General")
            )
        return jsonify({"status": "ok"})

    @app.route("/api/rules/delete", methods=["POST"])
    def flask_delete_rule():
        data = request.get_json() or {}
        p_name = data.get("process_name", "")
        if p_name:
            db_manager.delete_enforcement_rule(p_name)
        return jsonify({"status": "ok"})

    @app.route("/api/adjust-time", methods=["POST"])
    def flask_adjust_time():
        data = request.get_json() or {}
        delta = int(data.get("delta", 0))
        new_bal = db_manager.update_balance(delta, reason=f"Parental adjustment ({delta:+d}s)")
        if new_bal > 0 and enforcement.is_distraction_blocked():
            enforcement.unblock_distractions()
        return jsonify({"status": "ok", "new_balance": new_bal})

    @app.route("/api/set-time", methods=["POST"])
    def flask_set_time():
        data = request.get_json() or {}
        bal = int(data.get("balance", 0))
        new_bal = db_manager.reset_balance(bal)
        if new_bal > 0 and enforcement.is_distraction_blocked():
            enforcement.unblock_distractions()
        return jsonify({"status": "ok", "new_balance": new_bal})

    @app.route("/api/toggle-lock", methods=["POST"])
    def flask_toggle_lock():
        data = request.get_json() or {}
        locked = bool(data.get("locked", False))
        db_manager.set_blocked_status(locked)
        if locked:
            enforcement.block_distractions()
            curr = db_manager.get_child_state().get("current_process", "")
            if curr:
                enforcement.terminate_process_by_name(curr)
        else:
            if db_manager.get_current_balance() > 0:
                enforcement.unblock_distractions()
        return jsonify({"status": "ok", "is_locked": locked})

    @app.route("/api/kill-process", methods=["POST"])
    def flask_kill_process():
        data = request.get_json() or {}
        p_name = data.get("process_name", "")
        success = enforcement.terminate_process_by_name(p_name) if p_name else False
        return jsonify({"status": "ok", "terminated": success})

    @app.route("/api/toggle-web-filter", methods=["POST"])
    def flask_toggle_web_filter():
        blocked = enforcement.is_distraction_blocked()
        if blocked:
            enforcement.unblock_distractions()
        else:
            enforcement.block_distractions()
        return jsonify({"status": "ok", "hosts_blocked": enforcement.is_distraction_blocked()})

    @app.route("/api/logs", methods=["GET"])
    def flask_logs():
        return jsonify(db_manager.get_recent_logs(limit=15))

except ImportError:
    flask_available = False
    app = None


# Built-in ThreadingHTTPServer Fallback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


class BuiltinParentalHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_str):
        body = html_str.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(DASHBOARD_HTML)
        elif parsed.path == "/api/status":
            self._send_json(get_system_status_payload())
        elif parsed.path == "/api/processes":
            self._send_json(db_manager.get_tracked_processes(limit=100))
        elif parsed.path == "/api/rules":
            self._send_json(db_manager.get_enforcement_rules())
        elif parsed.path == "/api/logs":
            self._send_json(db_manager.get_recent_logs(limit=15))
        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if parsed.path == "/api/rules":
            p_name = payload.get("process_name", "")
            if p_name:
                db_manager.set_enforcement_rule(
                    process_name=p_name,
                    display_name=payload.get("display_name"),
                    time_limit_minutes=int(payload.get("time_limit_minutes", 60)),
                    is_blocked=int(payload.get("is_blocked", 0)),
                    action=payload.get("action", "terminate"),
                    category=payload.get("category", "General")
                )
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/rules/delete":
            p_name = payload.get("process_name", "")
            if p_name:
                db_manager.delete_enforcement_rule(p_name)
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/adjust-time":
            delta = int(payload.get("delta", 0))
            new_bal = db_manager.update_balance(delta, reason=f"Parental adjustment ({delta:+d}s)")
            if new_bal > 0 and enforcement.is_distraction_blocked():
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "new_balance": new_bal})

        elif parsed.path == "/api/set-time":
            bal = int(payload.get("balance", 0))
            new_bal = db_manager.reset_balance(bal)
            if new_bal > 0 and enforcement.is_distraction_blocked():
                enforcement.unblock_distractions()
            self._send_json({"status": "ok", "new_balance": new_bal})

        elif parsed.path == "/api/toggle-lock":
            locked = bool(payload.get("locked", False))
            db_manager.set_blocked_status(locked)
            if locked:
                enforcement.block_distractions()
                curr = db_manager.get_child_state().get("current_process", "")
                if curr:
                    enforcement.terminate_process_by_name(curr)
            else:
                if db_manager.get_current_balance() > 0:
                    enforcement.unblock_distractions()
            self._send_json({"status": "ok", "is_locked": locked})

        elif parsed.path == "/api/kill-process":
            p_name = payload.get("process_name", "")
            success = enforcement.terminate_process_by_name(p_name) if p_name else False
            self._send_json({"status": "ok", "terminated": success})

        elif parsed.path == "/api/toggle-web-filter":
            blocked = enforcement.is_distraction_blocked()
            if blocked:
                enforcement.unblock_distractions()
            else:
                enforcement.block_distractions()
            self._send_json({"status": "ok", "hosts_blocked": enforcement.is_distraction_blocked()})

        else:
            self.send_error(404, "Endpoint Not Found")

    def log_message(self, format, *args):
        pass


def run_server(port=PORT):
    db_manager.init_db()
    print("=" * 65)
    print(f" DEMON PARENTAL WEB DASHBOARD: http://localhost:{port}")
    print(f" Framework: {'Flask' if flask_available else 'Standard ThreadingHTTPServer'}")
    print(f" Database:  {db_manager.DEFAULT_DB_PATH}")
    print("=" * 65)

    if flask_available and app:
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer((HOST, port), BuiltinParentalHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    run_server()
