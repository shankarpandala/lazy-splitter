"""Simple web UI for lazy-splitter.

Provides a browser-based interface built with plain HTML, CSS, and vanilla
JavaScript.  No front-end framework is required -- all markup is served
from inline strings so there are zero template-file dependencies.

The web app is designed to be mounted as a sub-application of the main REST
API via::

    main_app.mount("/", create_web_app())

Pages:
    ``/``              -- Upload form with drag-and-drop support.
    ``/results``       -- View results for a completed job.
    ``/jobs/{job_id}`` -- Live job status with auto-refresh.

Python 3.8+ compatible.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared HTML fragments
# ---------------------------------------------------------------------------

_CSS = """\
:root {
    --bg: #f5f7fa;
    --card: #ffffff;
    --primary: #4f46e5;
    --primary-hover: #4338ca;
    --text: #1e293b;
    --muted: #64748b;
    --border: #e2e8f0;
    --success: #22c55e;
    --error: #ef4444;
    --warning: #f59e0b;
    --radius: 8px;
    --shadow: 0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
}
.container { max-width: 800px; margin: 0 auto; padding: 2rem 1rem; }
header {
    text-align: center;
    margin-bottom: 2rem;
}
header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--primary);
}
header p { color: var(--muted); font-size: 0.95rem; }
.card {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid var(--border);
}
.card h2 {
    font-size: 1.15rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
}
.tabs {
    display: flex;
    gap: 0;
    margin-bottom: 1.5rem;
    border-bottom: 2px solid var(--border);
}
.tab {
    padding: 0.6rem 1.2rem;
    cursor: pointer;
    border: none;
    background: none;
    color: var(--muted);
    font-size: 0.95rem;
    font-weight: 500;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.2s;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--primary); border-bottom-color: var(--primary); }
.tab-content { display: none; }
.tab-content.active { display: block; }
.drop-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    padding: 2rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    margin-bottom: 1rem;
}
.drop-zone:hover, .drop-zone.dragover {
    border-color: var(--primary);
    background: rgba(79, 70, 229, 0.04);
}
.drop-zone p { color: var(--muted); }
.drop-zone .file-name { color: var(--text); font-weight: 500; margin-top: 0.5rem; }
.form-group { margin-bottom: 1rem; }
.form-group label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    margin-bottom: 0.3rem;
    color: var(--muted);
}
.form-group select, .form-group input[type="text"], .form-group input[type="number"] {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 0.9rem;
    background: var(--card);
    color: var(--text);
}
.btn {
    display: inline-block;
    padding: 0.6rem 1.5rem;
    background: var(--primary);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    text-decoration: none;
}
.btn:hover { background: var(--primary-hover); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--border);
}
.btn-secondary:hover { background: var(--bg); }
.progress-bar {
    width: 100%;
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
    margin: 0.75rem 0;
}
.progress-bar .fill {
    height: 100%;
    background: var(--primary);
    border-radius: 4px;
    transition: width 0.3s;
    width: 0%;
}
.status-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
}
.status-pending { background: #fef3c7; color: #92400e; }
.status-processing { background: #dbeafe; color: #1e40af; }
.status-completed { background: #dcfce7; color: #166534; }
.status-failed { background: #fee2e2; color: #991b1b; }
.result-list { list-style: none; }
.result-list li {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
}
.result-list li:last-child { border-bottom: none; }
.error-msg { color: var(--error); font-size: 0.9rem; margin-top: 0.5rem; }
.hidden { display: none !important; }
footer {
    text-align: center;
    color: var(--muted);
    font-size: 0.8rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
}
"""

_JS = """\
(function() {
    'use strict';

    // ── Tab switching ──────────────────────────────────────────────────
    document.querySelectorAll('.tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            tab.classList.add('active');
            var target = document.getElementById(tab.dataset.tab);
            if (target) target.classList.add('active');
        });
    });

    // ── Drag & drop ────────────────────────────────────────────────────
    document.querySelectorAll('.drop-zone').forEach(function(zone) {
        var input = zone.querySelector('input[type="file"]');
        var nameEl = zone.querySelector('.file-name');

        zone.addEventListener('click', function() { if (input) input.click(); });

        zone.addEventListener('dragover', function(e) {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', function() {
            zone.classList.remove('dragover');
        });
        zone.addEventListener('drop', function(e) {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (input && e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                _showFiles(nameEl, e.dataTransfer.files);
            }
        });
        if (input) {
            input.addEventListener('change', function() {
                _showFiles(nameEl, input.files);
            });
        }
    });

    function _showFiles(el, files) {
        if (!el || !files || !files.length) return;
        var names = [];
        for (var i = 0; i < files.length; i++) names.push(files[i].name);
        el.textContent = names.join(', ');
    }

    // ── Form submission ────────────────────────────────────────────────
    window.submitOperation = function(op) {
        var form = document.getElementById('form-' + op);
        if (!form) return;

        var fd = new FormData(form);
        var statusEl = document.getElementById('status-area');
        var resultEl = document.getElementById('result-area');
        var errorEl = document.getElementById('error-area');
        var submitBtn = form.querySelector('button[type="submit"]');

        if (statusEl) statusEl.classList.add('hidden');
        if (resultEl) resultEl.classList.add('hidden');
        if (errorEl) { errorEl.classList.add('hidden'); errorEl.textContent = ''; }
        if (submitBtn) submitBtn.disabled = true;

        var endpoint = '/api/v1/' + op;

        fetch(endpoint, {
            method: 'POST',
            body: fd
        })
        .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
        .then(function(res) {
            if (submitBtn) submitBtn.disabled = false;
            if (!res.ok) {
                if (errorEl) {
                    errorEl.textContent = res.data.detail || 'An error occurred.';
                    errorEl.classList.remove('hidden');
                }
                return;
            }
            var data = res.data;
            if (data.job_id) {
                // Redirect to job status page.
                window.location.href = '/jobs/' + data.job_id;
            } else if (data.chapters) {
                // Preview result -- show inline.
                _showPreview(data);
            }
        })
        .catch(function(err) {
            if (submitBtn) submitBtn.disabled = false;
            if (errorEl) {
                errorEl.textContent = 'Network error: ' + err.message;
                errorEl.classList.remove('hidden');
            }
        });

        return false;  // Prevent default form submission.
    };

    function _showPreview(data) {
        var resultEl = document.getElementById('result-area');
        if (!resultEl) return;
        var html = '<h2>Preview: ' + (data.chapters.length) + ' chapter(s) found</h2>';
        html += '<p>Strategy: <strong>' + data.strategy_used + '</strong>';
        html += ' &middot; Total items: <strong>' + data.total_items + '</strong></p>';
        html += '<ul class="result-list">';
        data.chapters.forEach(function(ch, i) {
            html += '<li><strong>' + (i+1) + '.</strong> ' + ch.title;
            html += ' <span style="color:var(--muted)">(';
            html += ch.start + ' - ' + ch.end;
            html += ', confidence: ' + (ch.confidence * 100).toFixed(0) + '%';
            html += ')</span></li>';
        });
        html += '</ul>';
        resultEl.innerHTML = html;
        resultEl.classList.remove('hidden');
    }

    // ── Job polling (used on /jobs/{id} page) ──────────────────────────
    window.pollJob = function(jobId) {
        var statusEl = document.getElementById('job-status');
        var progressEl = document.getElementById('job-progress-fill');
        var progressText = document.getElementById('job-progress-text');
        var downloadEl = document.getElementById('job-download');
        var errorEl = document.getElementById('job-error');

        function poll() {
            fetch('/api/v1/jobs/' + jobId)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    // Update status badge.
                    if (statusEl) {
                        statusEl.className = 'status-badge status-' + data.status;
                        statusEl.textContent = data.status;
                    }
                    // Update progress.
                    if (progressEl) progressEl.style.width = data.progress + '%';
                    if (progressText) progressText.textContent = data.progress.toFixed(0) + '%';

                    if (data.status === 'completed') {
                        if (downloadEl) {
                            downloadEl.innerHTML = '<a class="btn" href="/api/v1/jobs/' + jobId + '/download">Download Results</a>';
                            downloadEl.classList.remove('hidden');
                        }
                        return;  // Stop polling.
                    }
                    if (data.status === 'failed') {
                        if (errorEl) {
                            errorEl.textContent = data.error || 'Job failed.';
                            errorEl.classList.remove('hidden');
                        }
                        return;  // Stop polling.
                    }
                    // Still processing -- poll again.
                    setTimeout(poll, 1500);
                })
                .catch(function() {
                    setTimeout(poll, 3000);
                });
        }
        poll();
    };
})();
"""


def _base_html(title: str, body: str) -> str:
    """Wrap *body* in a complete HTML page with shared styles and scripts."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <title>%s - lazy-splitter</title>\n"
        "  <style>%s</style>\n"
        "</head>\n"
        "<body>\n"
        "%s\n"
        "<script>%s</script>\n"
        "</body>\n"
        "</html>"
    ) % (title, _CSS, body, _JS)


# ---------------------------------------------------------------------------
# Page bodies
# ---------------------------------------------------------------------------

_UPLOAD_BODY = """\
<div class="container">
  <header>
    <h1>lazy-splitter</h1>
    <p>Split, merge, convert, and preview documents, audio, and video</p>
  </header>

  <div class="card">
    <div class="tabs">
      <button class="tab active" data-tab="tab-split">Split</button>
      <button class="tab" data-tab="tab-merge">Merge</button>
      <button class="tab" data-tab="tab-convert">Convert</button>
      <button class="tab" data-tab="tab-preview">Preview</button>
    </div>

    <!-- Split -->
    <div id="tab-split" class="tab-content active">
      <form id="form-split" onsubmit="return submitOperation('split')">
        <div class="drop-zone">
          <p>Drag &amp; drop a file here, or click to browse</p>
          <input type="file" name="file" style="display:none" required>
          <div class="file-name"></div>
        </div>
        <div class="form-group">
          <label for="split-strategy">Strategy</label>
          <select id="split-strategy" name="strategy">
            <option value="auto">Auto-detect</option>
            <option value="bookmarks">Bookmarks / TOC</option>
            <option value="heuristic">Heuristic</option>
            <option value="hybrid">Hybrid</option>
            <option value="regex">Regex pattern</option>
          </select>
        </div>
        <div class="form-group">
          <label for="split-sensitivity">Sensitivity</label>
          <select id="split-sensitivity" name="sensitivity">
            <option value="low">Low</option>
            <option value="medium" selected>Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <div class="form-group">
          <label for="split-pattern">Regex Pattern (optional)</label>
          <input type="text" id="split-pattern" name="pattern" placeholder="e.g. Chapter \\d+">
        </div>
        <div class="form-group">
          <label for="split-password">Password (optional)</label>
          <input type="text" id="split-password" name="password" placeholder="For encrypted files">
        </div>
        <div class="form-group">
          <label for="split-pages">Pages (optional)</label>
          <input type="text" id="split-pages" name="pages" placeholder="e.g. 1-5,8,10-12">
        </div>
        <button type="submit" class="btn">Split File</button>
      </form>
    </div>

    <!-- Merge -->
    <div id="tab-merge" class="tab-content">
      <form id="form-merge" onsubmit="return submitOperation('merge')">
        <div class="drop-zone">
          <p>Drag &amp; drop files here, or click to browse (select multiple)</p>
          <input type="file" name="files" style="display:none" multiple required>
          <div class="file-name"></div>
        </div>
        <div class="form-group">
          <label for="merge-format">Output Format (optional)</label>
          <select id="merge-format" name="output_format">
            <option value="">Auto-detect</option>
            <option value="pdf">PDF</option>
            <option value="epub">EPUB</option>
          </select>
        </div>
        <div class="form-group">
          <label>
            <input type="checkbox" name="generate_toc" value="true" checked>
            Generate table of contents
          </label>
        </div>
        <button type="submit" class="btn">Merge Files</button>
      </form>
    </div>

    <!-- Convert -->
    <div id="tab-convert" class="tab-content">
      <form id="form-convert" onsubmit="return submitOperation('convert')">
        <div class="drop-zone">
          <p>Drag &amp; drop a file here, or click to browse</p>
          <input type="file" name="file" style="display:none" required>
          <div class="file-name"></div>
        </div>
        <div class="form-group">
          <label for="convert-format">Output Format</label>
          <select id="convert-format" name="output_format" required>
            <option value="">Select format...</option>
            <option value="png">PNG</option>
            <option value="jpeg">JPEG</option>
            <option value="pdf">PDF</option>
            <option value="txt">Plain Text</option>
            <option value="mp3">MP3</option>
            <option value="wav">WAV</option>
            <option value="flac">FLAC</option>
          </select>
        </div>
        <div class="form-group">
          <label for="convert-quality">Quality (optional)</label>
          <input type="number" id="convert-quality" name="quality" min="1" max="100" placeholder="1-100">
        </div>
        <div class="form-group">
          <label for="convert-dpi">DPI (optional)</label>
          <input type="number" id="convert-dpi" name="dpi" min="72" max="600" placeholder="e.g. 150">
        </div>
        <button type="submit" class="btn">Convert File</button>
      </form>
    </div>

    <!-- Preview -->
    <div id="tab-preview" class="tab-content">
      <form id="form-preview" onsubmit="return submitOperation('preview')">
        <div class="drop-zone">
          <p>Drag &amp; drop a file here, or click to browse</p>
          <input type="file" name="file" style="display:none" required>
          <div class="file-name"></div>
        </div>
        <div class="form-group">
          <label for="preview-strategy">Strategy</label>
          <select id="preview-strategy" name="strategy">
            <option value="auto">Auto-detect</option>
            <option value="bookmarks">Bookmarks / TOC</option>
            <option value="heuristic">Heuristic</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </div>
        <div class="form-group">
          <label for="preview-sensitivity">Sensitivity</label>
          <select id="preview-sensitivity" name="sensitivity">
            <option value="low">Low</option>
            <option value="medium" selected>Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <button type="submit" class="btn">Preview Chapters</button>
      </form>
    </div>
  </div>

  <div id="error-area" class="error-msg hidden"></div>
  <div id="status-area" class="card hidden"></div>
  <div id="result-area" class="card hidden"></div>

  <footer>
    lazy-splitter &middot; <a href="/docs" style="color:var(--primary)">API Docs</a>
    &middot; <a href="/api/v1/health" style="color:var(--primary)">Health</a>
  </footer>
</div>
"""


def _job_status_body(job_id: str) -> str:
    """Return the HTML body for the job status page."""
    return (
        '<div class="container">\n'
        "  <header>\n"
        "    <h1>lazy-splitter</h1>\n"
        "    <p>Job Status</p>\n"
        "  </header>\n"
        '  <div class="card">\n'
        "    <h2>Job: %s</h2>\n"
        '    <p>Status: <span id="job-status" class="status-badge status-pending">pending</span></p>\n'
        '    <div class="progress-bar"><div id="job-progress-fill" class="fill"></div></div>\n'
        '    <p>Progress: <span id="job-progress-text">0%%</span></p>\n'
        '    <div id="job-download" class="hidden" style="margin-top:1rem;"></div>\n'
        '    <p id="job-error" class="error-msg hidden"></p>\n'
        "  </div>\n"
        '  <p><a href="/" class="btn btn-secondary">Back to Upload</a></p>\n'
        "  <footer>\n"
        '    lazy-splitter &middot; <a href="/docs" style="color:var(--primary)">API Docs</a>\n'
        "  </footer>\n"
        "</div>\n"
        "<script>pollJob('%s');</script>"
    ) % (job_id, job_id)


# ========================================================================
# Web app factory
# ========================================================================

def create_web_app() -> Any:
    """Create a FastAPI sub-application that serves the web UI.

    The returned app should be mounted on the main API app::

        main_app.mount("/", create_web_app())

    Returns:
        A :class:`fastapi.FastAPI` instance serving the web UI pages.

    Raises:
        ImportError: If ``fastapi`` is not installed.
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the web UI.  "
            "Install it with:  pip install fastapi"
        )

    web = FastAPI(
        title="lazy-splitter Web UI",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @web.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        """Serve the main upload page."""
        return _base_html("Upload", _UPLOAD_BODY)

    @web.get("/jobs/{job_id}", response_class=HTMLResponse, include_in_schema=False)
    async def job_page(job_id: str) -> str:
        """Serve the job status page."""
        return _base_html("Job %s" % job_id, _job_status_body(job_id))

    @web.get("/results", response_class=HTMLResponse, include_in_schema=False)
    async def results_page() -> str:
        """Serve a generic results page (redirects to upload if no job)."""
        body = (
            '<div class="container">\n'
            "  <header>\n"
            "    <h1>lazy-splitter</h1>\n"
            "    <p>Results</p>\n"
            "  </header>\n"
            '  <div class="card">\n'
            "    <p>No job selected.  "
            '    <a href="/">Go back to upload a file.</a></p>\n'
            "  </div>\n"
            "</div>"
        )
        return _base_html("Results", body)

    return web
