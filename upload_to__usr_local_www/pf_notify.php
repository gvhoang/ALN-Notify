<?php
/*
 * pf_notify.php — Trang quản lý pfSense Gateway Telegram Notifier
 * Upload: /usr/local/www/pf_notify.php
 */
require_once('guiconfig.inc');
$pgtitle = [gettext('Diagnostics'), 'PF Notify'];
include('head.inc');

define('PF_CONFIG_FILE', '/usr/local/etc/pf_notify/config.json');

$defaults = [
    'telegram_token'        => '',
    'telegram_chat_id'      => '',
    'log_files'             => ['/var/log/gateways.log', '/var/log/system.log', '/var/log/ppp.log'],
    'delay_seconds'         => 3,
    'spam_cooldown'         => 300,
    'gui_fail_threshold'    => 3,
    'retry_count'           => 3,
    'retry_backoff'         => 2,
    'rate_limit_per_min'    => 10,
];

$pf_cfg = $defaults;
if (file_exists(PF_CONFIG_FILE)) {
    $json = @json_decode(file_get_contents(PF_CONFIG_FILE), true);
    if (is_array($json)) { $pf_cfg = array_merge($defaults, $json); }
}
$log_files_str = implode("\n", (array)$pf_cfg['log_files']);
$log_count     = count((array)$pf_cfg['log_files']);
?>

<style>
/* ── SVG icon reset ─────────────────────────────────────────────────── */
#pfn-app svg { display:block; width:16px; height:16px; }
#pfn-app button, #pfn-app input, #pfn-app textarea, #pfn-app select {
    font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    letter-spacing: 0;
    cursor: pointer;
}
/* ── Tokens ─────────────────────────────────────────────────────────── */
#pfn-app {
    --bg:           #0f141d;
    --panel:        #171d29;
    --panel-2:      #1d2533;
    --line:         #2a3547;
    --line-strong:  #3a4658;
    --text:         #e7edf7;
    --muted:        #9aa7bb;
    --primary:      #4f8cff;
    --primary-dark: #3b75e8;
    --green:        #3dd68c;
    --green-soft:   #123629;
    --amber:        #f7c566;
    --amber-soft:   #3b2b12;
    --red:          #ff7b72;
    --red-soft:     #3a1c1d;
    --code:         #090d14;
    --shadow:       0 14px 40px rgba(0,0,0,.24);
    --radius:       8px;
    color: var(--text);
    font-size: 14px;
    line-height: 1.45;
}
/* ── Buttons ──────────────────────────────────────────────────────── */
#pfn-app .btn, #pfn-app .icon-btn {
    display: inline-flex; align-items: center; justify-content: center;
    gap: 8px; border: 1px solid transparent; border-radius: 7px;
    min-height: 34px; padding: 0 12px;
    color: var(--text); text-decoration: none !important;
    transition: background .12s, border-color .12s, color .12s;
    white-space: nowrap;
}
#pfn-app .icon-btn {
    width: 34px; padding: 0;
    background: rgba(255,255,255,.06); border-color: rgba(255,255,255,.12); color: #cdd5e3;
}
#pfn-app .icon-btn:hover { background: rgba(255,255,255,.12); }
#pfn-app .btn-primary  { background: var(--primary); color:#fff; border-color: var(--primary); }
#pfn-app .btn-primary:hover { background: var(--primary-dark); border-color: var(--primary-dark); color:#fff; }
#pfn-app .btn-secondary { background: #111722; border-color: var(--line-strong); color: var(--text); }
#pfn-app .btn-secondary:hover { background: #1a2332; color: var(--text); }
#pfn-app .btn-danger { background: #111722; border-color: #f2b8b5; color: var(--red); }
#pfn-app .btn-danger:hover { background: var(--red-soft); color: var(--red); }
#pfn-app .btn-ghost { background: transparent; border-color: transparent; color: var(--muted); }
#pfn-app .btn-ghost:hover { background: var(--panel-2); color: var(--text); }
/* ── Layout ─────────────────────────────────────────────────────────── */
#pfn-app .breadcrumb { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
#pfn-app .breadcrumb strong { color: var(--primary); font-weight: 700; }
#pfn-app .masthead {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 16px;
    display: grid; grid-template-columns: minmax(240px,1fr) auto; gap: 16px; align-items: center;
}
#pfn-app .title-row { display:flex; align-items:center; gap:12px; min-width:0; }
#pfn-app .app-mark {
    width:40px; height:40px; border-radius:8px;
    background: linear-gradient(145deg,#2563eb,#0f9f6e);
    color:#fff; display:grid; place-items:center; flex:0 0 auto;
}
#pfn-app h1 { margin:0; font-size:19px; line-height:1.2; font-weight:750; color: var(--text); }
#pfn-app .subtitle { margin-top:3px; color:var(--muted); font-size:13px; }
#pfn-app .status-group {
    display:grid; grid-template-columns:repeat(3, minmax(110px,1fr)); gap:8px;
}
#pfn-app .stat {
    border:1px solid var(--line); background:var(--panel-2);
    border-radius:7px; padding:8px 10px; min-width:0;
}
#pfn-app .stat b { display:block; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#pfn-app .stat span { display:block; color:var(--muted); font-size:11px; margin-top:2px; white-space:nowrap; }
#pfn-app .stat.stat-ok b { color: var(--green); }
#pfn-app .stat.stat-warn b { color: var(--amber); }
#pfn-app .stat.stat-err b { color: var(--red); }
/* ── Workspace ──────────────────────────────────────────────────────── */
#pfn-app .workspace {
    margin-top:14px;
    display:grid; grid-template-columns: minmax(0,1fr) 360px; gap:14px; align-items:start;
}
#pfn-app .stack { display:grid; gap:12px; }
#pfn-app .panel { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }
#pfn-app .panel-head {
    min-height:44px; display:flex; align-items:center; justify-content:space-between;
    gap:12px; padding:0 14px; border-bottom:1px solid var(--line); background:var(--panel-2);
}
#pfn-app .panel-title { display:inline-flex; align-items:center; gap:9px; font-weight:750; color:var(--text); min-width:0; }
#pfn-app .panel-body { padding:14px; }
#pfn-app .grid-2 { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
#pfn-app .grid-3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
#pfn-app .field { min-width:0; }
#pfn-app label { display:block; font-size:12px; font-weight:700; color:#7a8da8; margin-bottom:6px; }
#pfn-app .control-row { display:flex; gap:8px; align-items:stretch; }
#pfn-app .input, #pfn-app textarea {
    width:100%; min-height:36px;
    border:1px solid var(--line-strong); border-radius:7px;
    background:#111722; color:var(--text);
    padding:8px 10px; outline:none;
    transition: border-color .12s, box-shadow .12s;
}
#pfn-app textarea { min-height:104px; resize:vertical; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; line-height:1.55; }
#pfn-app .input:focus, #pfn-app textarea:focus {
    border-color:#7aa7ff; box-shadow:0 0 0 3px rgba(37,99,235,.13);
}
#pfn-app .token-input { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
#pfn-app .hint { margin:6px 0 0; color:var(--muted); font-size:12px; }
/* ── Notice / Alert ─────────────────────────────────────────────────── */
#pfn-app .notice {
    margin-top:12px; padding:10px 12px; border-radius:7px;
    display:flex; align-items:center; gap:8px; font-weight:650; font-size:13px;
}
#pfn-app .notice[hidden] { display:none !important; }
#pfn-app .notice-ok  { border:1px solid #a7e5c4; background:var(--green-soft); color:#3dd68c; }
#pfn-app .notice-err { border:1px solid #f2b8b5; background:var(--red-soft);   color:var(--red); }
#pfn-app .notice-info{ border:1px solid #4f8cff; background:#0f1e3a;           color:#7aa7ff; }
/* ── Footer actions ─────────────────────────────────────────────────── */
#pfn-app .footer-actions {
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
    padding:12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;
}
/* ── Side (sticky) ──────────────────────────────────────────────────── */
#pfn-app .side { position:sticky; top:12px; display:grid; gap:12px; }
#pfn-app .service-row {
    display:grid; grid-template-columns:1fr auto; gap:8px; align-items:center;
    padding:10px 0; border-bottom:1px solid var(--line);
}
#pfn-app .service-row:last-child { border-bottom:0; }
#pfn-app .service-row span { color:var(--muted); font-size:13px; }
#pfn-app .service-row strong { font-size:13px; }
#pfn-app .badge {
    display:inline-flex; align-items:center; gap:6px;
    min-height:26px; padding:0 10px; border-radius:999px;
    font-size:12px; font-weight:750; white-space:nowrap;
}
#pfn-app .badge-ok   { color:#067647; background:var(--green-soft); border:1px solid #a7e5c4; }
#pfn-app .badge-warn { color:var(--amber); background:var(--amber-soft); border:1px solid #ffd88a; }
#pfn-app .badge-err  { color:var(--red);   background:var(--red-soft);   border:1px solid #f2b8b5; }
#pfn-app .dot { width:7px; height:7px; border-radius:50%; background:currentColor; }
#pfn-app .button-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:10px; }
/* ── Log ────────────────────────────────────────────────────────────── */
#pfn-app .log-toolbar { display:flex; align-items:center; gap:8px; }
#pfn-app .pfn-select {
    min-height:32px; border:1px solid var(--line-strong); border-radius:7px;
    background:#111722; color:var(--text); padding:0 8px; font-size:13px;
}
#pfn-app pre.log {
    margin:0; background:var(--code); color:#d1fae5;
    min-height:284px; max-height:380px; overflow:auto;
    padding:12px; border-radius:7px;
    font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    white-space:pre-wrap;
}
#pfn-app pre.log::-webkit-scrollbar { width:5px; }
#pfn-app pre.log::-webkit-scrollbar-thumb { background:#2a3547; border-radius:3px; }
/* ── Svc msg ────────────────────────────────────────────────────────── */
#pfn-svc-msg { font-size:12px; color:var(--muted); font-style:italic; }
/* ── Responsive ─────────────────────────────────────────────────────── */
@media (max-width:1080px) {
    #pfn-app .masthead { grid-template-columns:1fr; }
    #pfn-app .status-group { grid-template-columns:repeat(3,minmax(0,1fr)); }
    #pfn-app .workspace { grid-template-columns:1fr; }
    #pfn-app .side { position:static; }
}
@media (max-width:720px) {
    #pfn-app .grid-2, #pfn-app .grid-3 { grid-template-columns:1fr; }
    #pfn-app .status-group { grid-template-columns:1fr; }
    #pfn-app .button-grid { grid-template-columns:1fr; }
}
</style>

<!-- SVG sprite -->
<svg aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden">
  <symbol id="pfn-bell"     viewBox="0 0 24 24"><path fill="currentColor" d="M12 22a2.4 2.4 0 0 0 2.3-1.7H9.7A2.4 2.4 0 0 0 12 22Zm7-5-1.7-2.3V10a5.3 5.3 0 0 0-4-5.1V4a1.3 1.3 0 0 0-2.6 0v.9a5.3 5.3 0 0 0-4 5.1v4.7L5 17v1.3h14V17Z"/></symbol>
  <symbol id="pfn-save"     viewBox="0 0 24 24"><path fill="currentColor" d="M5 3h12l2 2v16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 2v5h9V5H7Zm0 10v4h10v-4H7Z"/></symbol>
  <symbol id="pfn-send"     viewBox="0 0 24 24"><path fill="currentColor" d="m3 11 18-8-5.4 18-3.7-7-6.9 4 3.8-6L3 11Zm6.3 1.2 3.5.8 2 3.7 2.9-9.7-8.4 5.2Z"/></symbol>
  <symbol id="pfn-eye"      viewBox="0 0 24 24"><path fill="currentColor" d="M12 5c5.4 0 9 5.5 9 7s-3.6 7-9 7-9-5.5-9-7 3.6-7 9-7Zm0 3.5A3.5 3.5 0 1 0 12 15.5 3.5 3.5 0 0 0 12 8.5Zm0 2A1.5 1.5 0 1 1 12 13.5 1.5 1.5 0 0 1 12 10.5Z"/></symbol>
  <symbol id="pfn-play"     viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7L8 5Z"/></symbol>
  <symbol id="pfn-stop"     viewBox="0 0 24 24"><path fill="currentColor" d="M6 6h12v12H6z"/></symbol>
  <symbol id="pfn-refresh"  viewBox="0 0 24 24"><path fill="currentColor" d="M17.7 6.3A8 8 0 1 0 20 12h-2a6 6 0 1 1-1.8-4.3L13 11h8V3l-3.3 3.3Z"/></symbol>
  <symbol id="pfn-sliders"  viewBox="0 0 24 24"><path fill="currentColor" d="M4 7h9a3 3 0 0 0 5.8 0H20V5h-1.2A3 3 0 0 0 13 5H4v2Zm0 12h1.2a3 3 0 0 0 5.8 0h9v-2h-9a3 3 0 0 0-5.8 0H4v2Zm0-6h4a3 3 0 0 0 5.8 0H20v-2h-6.2A3 3 0 0 0 8 11H4v2Z"/></symbol>
  <symbol id="pfn-terminal" viewBox="0 0 24 24"><path fill="currentColor" d="M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm2.2 4.4L9 12l-2.8 2.6 1.3 1.4 4.2-4-4.2-4-1.3 1.4ZM12 15h6v-2h-6v2Z"/></symbol>
  <symbol id="pfn-check"    viewBox="0 0 24 24"><path fill="currentColor" d="m9.5 16.6-4.1-4.1L4 13.9 9.5 19 20 8.5 18.6 7 9.5 16.6Z"/></symbol>
  <symbol id="pfn-folder"   viewBox="0 0 24 24"><path fill="currentColor" d="M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2Z"/></symbol>
</svg>

<div id="pfn-app">

  <div class="breadcrumb">Diagnostics / <strong>PF Notify</strong></div>

  <!-- Masthead -->
  <section class="masthead">
    <div class="title-row">
      <div class="app-mark"><svg><use href="#pfn-bell"></use></svg></div>
      <div>
        <h1>PF Notify</h1>
        <div class="subtitle">Telegram Gateway Notifier cho pfSense</div>
      </div>
    </div>
    <div class="status-group">
      <div class="stat" id="stat-svc">
        <b id="stat-svc-val">...</b><span>daemon</span>
      </div>
      <div class="stat">
        <b><?= $log_count ?> file</b><span>đang theo dõi</span>
      </div>
      <div class="stat">
        <b><?= (int)$pf_cfg['rate_limit_per_min'] ?>/phút</b><span>rate limit</span>
      </div>
    </div>
  </section>

  <!-- Workspace -->
  <section class="workspace">
    <div class="stack">

      <!-- Telegram -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-send"></use></svg> Telegram</div>
          <button class="btn btn-secondary" id="pfn-test-btn"><svg><use href="#pfn-send"></use></svg> Test</button>
        </div>
        <div class="panel-body">
          <div class="grid-2">
            <div class="field">
              <label for="telegram_token">Bot Token</label>
              <div class="control-row">
                <input class="input token-input" id="telegram_token" type="password"
                       value="<?= htmlspecialchars($pf_cfg['telegram_token']) ?>"
                       autocomplete="off" placeholder="1234567890:AAFxxxx...">
                <button class="icon-btn" id="pfn-token-toggle" type="button" title="Hiện/ẩn token">
                  <svg><use href="#pfn-eye"></use></svg>
                </button>
              </div>
              <p class="hint">Lấy từ @BotFather trên Telegram</p>
            </div>
            <div class="field">
              <label for="telegram_chat_id">Chat ID</label>
              <input class="input token-input" id="telegram_chat_id" type="text"
                     value="<?= htmlspecialchars($pf_cfg['telegram_chat_id']) ?>"
                     autocomplete="off" placeholder="1015285796">
              <p class="hint">ID user hoặc group nhận thông báo</p>
            </div>
          </div>
          <div id="pfn-test-result" class="notice" hidden></div>
        </div>
      </section>

      <!-- File Log -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-folder"></use></svg> File Log</div>
          <small style="color:var(--muted);font-size:12px;"><?= $log_count ?> entries</small>
        </div>
        <div class="panel-body">
          <div class="field">
            <label for="log_files">Danh sách file log <span style="font-weight:400;">(mỗi file một dòng)</span></label>
            <textarea class="input" id="log_files" rows="4"><?= htmlspecialchars($log_files_str) ?></textarea>
          </div>
        </div>
      </section>

      <!-- Cảnh báo -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-sliders"></use></svg> Cảnh Báo</div>
        </div>
        <div class="panel-body">
          <div class="grid-3">
            <div class="field">
              <label for="delay_seconds">Delay cảnh báo</label>
              <input class="input" id="delay_seconds" type="number"
                     min="0" max="60" value="<?= (int)$pf_cfg['delay_seconds'] ?>">
              <p class="hint">giây — chống flap</p>
            </div>
            <div class="field">
              <label for="spam_cooldown">Cooldown chống spam</label>
              <input class="input" id="spam_cooldown" type="number"
                     min="0" max="3600" value="<?= (int)$pf_cfg['spam_cooldown'] ?>">
              <p class="hint">giây</p>
            </div>
            <div class="field">
              <label for="gui_fail_threshold">Sai mật khẩu GUI</label>
              <input class="input" id="gui_fail_threshold" type="number"
                     min="1" max="20" value="<?= (int)$pf_cfg['gui_fail_threshold'] ?>">
              <p class="hint">lần trước khi cảnh báo</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Retry & Rate Limit -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-refresh"></use></svg> Retry &amp; Rate Limit</div>
        </div>
        <div class="panel-body">
          <div class="grid-3">
            <div class="field">
              <label for="retry_count">Số lần retry</label>
              <input class="input" id="retry_count" type="number"
                     min="0" max="10" value="<?= (int)$pf_cfg['retry_count'] ?>">
            </div>
            <div class="field">
              <label for="retry_backoff">Backoff</label>
              <input class="input" id="retry_backoff" type="number"
                     min="1" max="30" value="<?= (int)$pf_cfg['retry_backoff'] ?>">
              <p class="hint">giây, nhân đôi mỗi lần</p>
            </div>
            <div class="field">
              <label for="rate_limit_per_min">Rate limit</label>
              <input class="input" id="rate_limit_per_min" type="number"
                     min="0" max="120" value="<?= (int)$pf_cfg['rate_limit_per_min'] ?>">
              <p class="hint">tin/phút (0 = không giới hạn)</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Footer actions -->
      <div class="footer-actions">
        <button class="btn btn-primary" id="pfn-save-btn">
          <svg><use href="#pfn-save"></use></svg> Lưu cấu hình
        </button>
        <button class="btn btn-secondary" id="pfn-reload-btn" style="display:none;">
          <svg><use href="#pfn-refresh"></use></svg> Reload service
        </button>
        <div id="pfn-save-result" class="notice" hidden style="margin:0;"></div>
      </div>

    </div><!-- /stack -->

    <!-- Sidebar -->
    <aside class="side">

      <!-- Dịch vụ -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-play"></use></svg> Dịch Vụ</div>
          <span class="badge badge-err" id="pfn-svc-badge">
            <span class="dot"></span>
            <span id="pfn-svc-badge-text">...</span>
          </span>
        </div>
        <div class="panel-body">
          <div class="service-row">
            <span>Process</span>
            <strong id="pfn-pid-text">—</strong>
          </div>
          <div class="service-row">
            <span>Config</span>
            <span id="pfn-cfg-badge" class="badge badge-ok">valid</span>
          </div>
          <div class="service-row" style="border-bottom:0;padding-bottom:0;">
            <span id="pfn-svc-msg"></span>
          </div>
          <div class="button-grid">
            <button class="btn btn-secondary" id="btn-start">
              <svg><use href="#pfn-play"></use></svg> Start
            </button>
            <button class="btn btn-danger" id="btn-stop">
              <svg><use href="#pfn-stop"></use></svg> Stop
            </button>
            <button class="btn btn-secondary" id="btn-restart">
              <svg><use href="#pfn-refresh"></use></svg> Restart
            </button>
            <button class="btn btn-secondary" id="btn-reload">
              <svg><use href="#pfn-refresh"></use></svg> Reload
            </button>
          </div>
        </div>
      </section>

      <!-- Log -->
      <section class="panel">
        <div class="panel-head">
          <div class="panel-title"><svg><use href="#pfn-terminal"></use></svg> Log</div>
          <div class="log-toolbar">
            <select class="pfn-select" id="pfn-log-lines">
              <option value="20">20</option>
              <option value="50" selected>50</option>
              <option value="100">100</option>
              <option value="200">200</option>
            </select>
            <button class="btn btn-ghost" id="btn-refresh-log" title="Làm mới">
              <svg><use href="#pfn-refresh"></use></svg>
            </button>
            <label style="display:flex;align-items:center;gap:5px;font-size:12px;font-weight:400;color:var(--muted);cursor:pointer;margin:0;">
              <input type="checkbox" id="pfn-auto-refresh" checked style="cursor:pointer;"> Auto
            </label>
          </div>
        </div>
        <div class="panel-body" style="padding:0;">
          <pre class="log" id="pfn-log-box">Đang tải...</pre>
        </div>
      </section>

    </aside>
  </section>
</div><!-- /#pfn-app -->

<?php include('foot.inc'); ?>

<script>
(function () {
    var API      = '/pf_notify_api.php';
    var logTimer = null;

    function apiPost(action, extra, cb) {
        $.ajax({
            url: API, type: 'POST',
            contentType: 'application/x-www-form-urlencoded',
            data: $.extend({ action: action }, extra || {}),
            dataType: 'json',
            success: cb,
            error: function (x) { cb({ ok: false, error: x.statusText }); }
        });
    }
    function apiGet(action, params, cb) {
        $.ajax({
            url: API, type: 'GET',
            contentType: 'application/x-www-form-urlencoded',
            data: $.extend({ action: action }, params || {}),
            dataType: 'json',
            success: cb,
            error: function (x) { cb({ ok: false, error: x.statusText }); }
        });
    }

    // ── Status ────────────────────────────────────────────────────────────
    function updateStatus(status) {
        var $b  = $('#pfn-svc-badge');
        var $bt = $('#pfn-svc-badge-text');
        var $st = $('#stat-svc-val');
        var $pid = $('#pfn-pid-text');
        $b.removeClass('badge-ok badge-warn badge-err');
        if (status.running) {
            $b.addClass('badge-ok'); $bt.text('Running');
            $st.text('Đang chạy'); $('#stat-svc').addClass('stat-ok').removeClass('stat-err stat-warn');
            $pid.text('PID ' + status.pid);
        } else if (status.pid) {
            $b.addClass('badge-warn'); $bt.text('Stale PID');
            $st.text('Stale'); $('#stat-svc').addClass('stat-warn').removeClass('stat-ok stat-err');
            $pid.text('PID ' + status.pid + ' (dead)');
        } else {
            $b.addClass('badge-err'); $bt.text('Stopped');
            $st.text('Dừng'); $('#stat-svc').addClass('stat-err').removeClass('stat-ok stat-warn');
            $pid.text('—');
        }
    }
    function refreshStatus() {
        apiGet('status', {}, function (r) { if (r && r.ok) updateStatus(r.status); });
    }

    // ── Log ───────────────────────────────────────────────────────────────
    function refreshLog() {
        apiGet('log', { lines: $('#pfn-log-lines').val() }, function (r) {
            var $b = $('#pfn-log-box');
            $b.text(r.log || '(log trống)');
            $b.scrollTop($b[0].scrollHeight);
        });
    }
    function startAutoRefresh() {
        stopAutoRefresh();
        logTimer = setInterval(function () { refreshLog(); refreshStatus(); }, 5000);
    }
    function stopAutoRefresh() { if (logTimer) { clearInterval(logTimer); logTimer = null; } }

    $('#btn-refresh-log').click(refreshLog);
    $('#pfn-log-lines').change(refreshLog);
    $('#pfn-auto-refresh').change(function () {
        if ($(this).is(':checked')) startAutoRefresh(); else stopAutoRefresh();
    });

    // ── Service control ───────────────────────────────────────────────────
    function svcAction(action) {
        $('#pfn-svc-msg').text('Đang ' + action + '...');
        apiPost(action, {}, function (r) {
            $('#pfn-svc-msg').text(r.output || '');
            if (r.status) updateStatus(r.status);
            refreshLog();
        });
    }
    $('#btn-start').click(function ()   { svcAction('start'); });
    $('#btn-stop').click(function ()    { svcAction('stop'); });
    $('#btn-restart').click(function () { svcAction('restart'); });
    $('#btn-reload').click(function ()  { svcAction('reload'); });

    // ── Token toggle ──────────────────────────────────────────────────────
    $('#pfn-token-toggle').click(function () {
        var $t = $('#telegram_token');
        $t.attr('type', $t.attr('type') === 'password' ? 'text' : 'password');
    });

    // ── Test ──────────────────────────────────────────────────────────────
    $('#pfn-test-btn').click(function () {
        var $r = $('#pfn-test-result');
        $r.removeClass('notice-ok notice-err').addClass('notice-info')
          .html('<svg><use href="#pfn-refresh"></use></svg> Đang gửi...').removeAttr('hidden');
        apiPost('test', {}, function (resp) {
            if (resp.ok) {
                $r.removeClass('notice-info notice-err').addClass('notice-ok')
                  .html('<svg><use href="#pfn-check"></use></svg> Tin test đã gửi thành công tới Telegram');
            } else {
                $r.removeClass('notice-info notice-ok').addClass('notice-err')
                  .html('<svg><use href="#pfn-stop"></use></svg> ' + (resp.error || 'Thất bại'));
            }
        });
    });

    // ── Save ──────────────────────────────────────────────────────────────
    $('#pfn-save-btn').click(function () {
        var $r   = $('#pfn-save-result');
        var logs = [];
        $.each($('#log_files').val().split('\n'), function (_, l) {
            l = $.trim(l); if (l) logs.push(l);
        });
        var data = {
            telegram_token:     $.trim($('#telegram_token').val()),
            telegram_chat_id:   $.trim($('#telegram_chat_id').val()),
            log_files:          logs,
            delay_seconds:      parseInt($('#delay_seconds').val(), 10),
            spam_cooldown:      parseInt($('#spam_cooldown').val(), 10),
            gui_fail_threshold: parseInt($('#gui_fail_threshold').val(), 10),
            retry_count:        parseInt($('#retry_count').val(), 10),
            retry_backoff:      parseInt($('#retry_backoff').val(), 10),
            rate_limit_per_min: parseInt($('#rate_limit_per_min').val(), 10)
        };
        $r.attr('hidden', true);
        $.ajax({
            url: API, type: 'POST',
            contentType: 'application/x-www-form-urlencoded',
            data: { action: 'save', config: JSON.stringify(data) },
            dataType: 'json',
            success: function (r) {
                if (r.ok) {
                    $r.removeClass('notice-err').addClass('notice notice-ok')
                      .html('<svg><use href="#pfn-check"></use></svg> ' + r.message)
                      .removeAttr('hidden');
                    $('#pfn-reload-btn').show();
                } else {
                    $r.removeClass('notice-ok').addClass('notice notice-err')
                      .html('<svg><use href="#pfn-stop"></use></svg> ' + (r.error || 'Lỗi'))
                      .removeAttr('hidden');
                }
            },
            error: function () {
                $r.removeClass('notice-ok').addClass('notice notice-err')
                  .html('<svg><use href="#pfn-stop"></use></svg> Lỗi kết nối API').removeAttr('hidden');
            }
        });
    });

    $('#pfn-reload-btn').click(function () {
        svcAction('reload'); $(this).hide();
    });

    // ── Init ──────────────────────────────────────────────────────────────
    refreshStatus();
    refreshLog();
    startAutoRefresh();
})();
</script>