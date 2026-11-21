let currentRcaMarkdown = "";
let healedCount = 0;

async function refreshActivity() {
    try {
        const res = await fetch('/api/activity');
        const data = await res.json();
        const logBox = document.getElementById('activity-log');
        logBox.innerHTML = '';
        data.activity.forEach(entry => {
            const div = document.createElement('div');
            let cls = 'log-info';
            if (entry.level === 'WARNING') cls = 'log-warning';
            if (entry.level === 'ERROR') cls = 'log-error';
            if (entry.message.includes('✅') || entry.message.includes('RESOLVED')) cls = 'log-success';
            
            div.className = `log-entry ${cls}`;
            div.innerHTML = `<span class="log-time">${entry.timestamp}</span> ${escapeHtml(entry.message)}`;
            logBox.appendChild(div);
        });
        logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {
        console.error("Failed to load activity:", e);
    }
}

async function runScenario(scenarioId) {
    appendLog(`[ACTION] User triggered scenario: ${scenarioId}...`, 'log-warning');
    const rcaContainer = document.getElementById('rca-container');
    rcaContainer.innerHTML = '<div style="text-align:center; padding-top:100px; color:#58a6ff;">🤖 DevOps Agent analyzing failure logs and cluster telemetry...</div>';

    try {
        const res = await fetch(`/api/scenarios/run/${scenarioId}`, { method: 'POST' });
        const data = await res.json();
        
        if (data.type === 'drift') {
            renderDriftResult(data.drift_report);
        } else if (data.incident) {
            renderIncidentResult(data.incident);
            healedCount++;
            document.getElementById('stat-incidents').innerText = healedCount;
        }
        
        await refreshActivity();
    } catch (err) {
        appendLog(`[ERROR] Scenario execution error: ${err.message}`, 'log-error');
        rcaContainer.innerHTML = `<div style="color:#f85149;">Error running scenario: ${escapeHtml(err.message)}</div>`;
    }
}

function renderIncidentResult(incident) {
    currentRcaMarkdown = incident.rca_markdown;
    document.getElementById('rca-actions').style.display = 'block';
    const rcaContainer = document.getElementById('rca-container');

    const diag = incident.diagnosis;
    const plan = incident.plan;
    const ver = incident.verification;

    let diffHtml = '';
    if (plan.diff) {
        const lines = plan.diff.split('\n').map(l => {
            if (l.startsWith('+') && !l.startsWith('+++')) return `<span class="diff-add">${escapeHtml(l)}</span>`;
            if (l.startsWith('-') && !l.startsWith('---')) return `<span class="diff-del">${escapeHtml(l)}</span>`;
            return `<span>${escapeHtml(l)}</span>`;
        }).join('');
        diffHtml = `<div class="diff-box">${lines}</div>`;
    }

    const badgeCls = ver.verified ? 'badge-success' : (ver.rollback_triggered ? 'badge-purple' : 'badge-danger');
    const badgeText = ver.verified ? 'HEALED & VERIFIED' : (ver.rollback_triggered ? 'ROLLED BACK' : 'FAILED');

    rcaContainer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <h2 style="font-size:16px;">${escapeHtml(incident.resource)} &bull; ${escapeHtml(diag.failure_type)}</h2>
            <span class="badge ${badgeCls}">${badgeText}</span>
        </div>
        <p style="color:#8b949e; font-size:13px; margin-bottom:12px;"><strong>Root Cause:</strong> ${escapeHtml(diag.root_cause)}</p>
        
        <h4 style="margin-top:14px; font-size:14px;">🛠️ Synthesized Remediation Patch:</h4>
        ${diffHtml}

        <h4 style="margin-top:14px; font-size:14px;">🩺 Verification & Health Checks:</h4>
        <ul style="padding-left: 20px; font-size: 13px; color: #8b949e; margin-top: 6px;">
            ${ver.details.map(d => `<li>${escapeHtml(d)}</li>`).join('')}
        </ul>

        <div style="margin-top: 18px; padding-top: 12px; border-top: 1px solid #30363d; font-size: 12px; color: #8b949e;">
            <strong>Incident ID:</strong> <code>${incident.incident_id}</code> | <strong>MTTR:</strong> ${incident.duration_seconds}s
        </div>
    `;
}

function renderDriftResult(drift) {
    const rcaContainer = document.getElementById('rca-container');
    document.getElementById('stat-drift').innerText = drift.drift_detected ? `${drift.drift_count} Drifts Found` : "Synchronized";
    document.getElementById('stat-drift').className = drift.drift_detected ? "stat-value text-orange" : "stat-value text-green";

    let diffLines = drift.differences.map(d => {
        return `<div style="margin-bottom:8px;">
            <code>${escapeHtml(d.path)}</code>: 
            <span class="diff-del">Desired: ${JSON.stringify(d.desired)}</span> 
            <span class="diff-add">Live: ${JSON.stringify(d.actual)}</span>
        </div>`;
    }).join('');

    rcaContainer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <h2 style="font-size:16px;">IaC Configuration Drift Report: ${escapeHtml(drift.resource_name)}</h2>
            <span class="badge badge-purple">${escapeHtml(drift.reconciliation_action)}</span>
        </div>
        <p style="color:#8b949e; font-size:13px; margin-bottom:12px;">
            Agent scanned live cluster state vs declarative Git manifests. Found <strong>${drift.drift_count}</strong> out-of-band modifications.
        </p>
        <div class="diff-box">${diffLines}</div>
        <p style="font-size:12px; color:#58a6ff;">Recommended Action: Trigger auto-reconciliation to restore Git baseline.</p>
    `;
}

function copyRCA() {
    if (currentRcaMarkdown) {
        navigator.clipboard.writeText(currentRcaMarkdown);
        alert("Markdown RCA copied to clipboard!");
    }
}

function appendLog(msg, cls = 'log-info') {
    const logBox = document.getElementById('activity-log');
    const div = document.createElement('div');
    const now = new Date().toTimeString().split(' ')[0];
    div.className = `log-entry ${cls}`;
    div.innerHTML = `<span class="log-time">${now}</span> ${escapeHtml(msg)}`;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Auto-poll activity
setInterval(refreshActivity, 5000);
window.onload = refreshActivity;
