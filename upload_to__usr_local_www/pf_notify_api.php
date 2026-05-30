<?php
/*
 * pf_notify_api.php — AJAX API cho trang quản lý pf_notify
 * Upload: /usr/local/www/pf_notify_api.php
 */

require_once('guiconfig.inc');
header('Content-Type: application/json; charset=utf-8');

define('PF_CONFIG_FILE', '/usr/local/etc/pf_notify/config.json');
define('PF_PIDFILE',     '/var/run/pf_notify.pid');
define('PF_LOGFILE',     '/var/log/pf_notify.log');
define('PF_RC',          '/usr/local/etc/rc.d/pf_notify.sh');
define('PF_SCRIPT',      '/usr/local/sbin/pf_notify.py');
define('PF_PYTHON',      '/usr/local/bin/python3.11');

function pf_get_status() {
    if (!file_exists(PF_PIDFILE)) {
        return ['running' => false, 'pid' => null, 'label' => 'Không chạy'];
    }
    $pid = trim(file_get_contents(PF_PIDFILE));
    if (!$pid) {
        return ['running' => false, 'pid' => null, 'label' => 'Không chạy'];
    }
    if (posix_kill((int)$pid, 0)) {
        return ['running' => true, 'pid' => $pid, 'label' => "Đang chạy (PID: $pid)"];
    }
    return ['running' => false, 'pid' => $pid, 'label' => "Lỗi: PID $pid không tồn tại (stale)"];
}

function pf_load_config() {
    $defaults = [
        'telegram_token'            => '',
        'telegram_chat_id'          => '',
        'log_files'                 => ['/var/log/gateways.log', '/var/log/system.log', '/var/log/ppp.log'],
        'state_file'                => '/var/db/pf_notify/state.json',
        'delay_seconds'             => 3,
        'spam_cooldown'             => 300,
        'high_loss_threshold'       => 20,
        'critical_loss_threshold'   => 80,
        'gui_fail_threshold'        => 3,
        'retry_count'               => 3,
        'retry_backoff'             => 2,
        'rate_limit_per_min'        => 10,
        'use_topics'                => false,
        'topic_name'                => '',
        'topic_thread_id'           => 0,
    ];
    if (file_exists(PF_CONFIG_FILE)) {
        $json = @json_decode(file_get_contents(PF_CONFIG_FILE), true);
        if (is_array($json)) {
            return array_merge($defaults, $json);
        }
    }
    return $defaults;
}

function pf_run_rc($cmd) {
    $allowed = ['start', 'stop', 'restart', 'reload'];
    if (!in_array($cmd, $allowed, true)) {
        return ['ok' => false, 'output' => 'Lệnh không hợp lệ'];
    }
    $out = shell_exec(PF_RC . ' ' . escapeshellarg($cmd) . ' 2>&1');
    return ['ok' => true, 'output' => trim($out)];
}

// ── Xác minh CSRF + auth ─────────────────────────────────────────────────
// guiconfig.inc đã enforce authentication (redirect nếu chưa đăng nhập).
// Với write actions, thêm csrf_check() để ngăn CSRF attack.
$action = $_REQUEST['action'] ?? '';
$write_actions = ['start', 'stop', 'restart', 'reload', 'save', 'test', 'reset_topic'];
if (in_array($action, $write_actions, true)) {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        echo json_encode(['ok' => false, 'error' => 'POST required']);
        exit;
    }
    // Kiểm tra CSRF token pfSense (csrf-magic.js tự inject __csrf_magic vào POST)
    if (function_exists('csrf_check') && !csrf_check(false)) {
        echo json_encode(['ok' => false, 'error' => 'CSRF token không hợp lệ']);
        exit;
    }
}

// ── Dispatch ──────────────────────────────────────────────────────────────
switch ($action) {

    case 'status':
        echo json_encode(['ok' => true, 'status' => pf_get_status()]);
        break;

    case 'start':
    case 'stop':
    case 'restart':
    case 'reload':
        $res = pf_run_rc($action);
        sleep(1);
        $res['status'] = pf_get_status();
        echo json_encode($res);
        break;

    case 'log':
        $lines = (int)($_GET['lines'] ?? 30);
        $lines = max(10, min(200, $lines));
        if (file_exists(PF_LOGFILE)) {
            $out = shell_exec('tail -' . $lines . ' ' . escapeshellarg(PF_LOGFILE) . ' 2>&1');
            echo json_encode(['ok' => true, 'log' => $out ?: '']);
        } else {
            echo json_encode(['ok' => false, 'log' => 'File log không tìm thấy: ' . PF_LOGFILE]);
        }
        break;

    case 'save':
        // Nhận data từ form field (tương thích CSRF pfSense)
        $body = $_POST['config'] ?? file_get_contents('php://input');
        $data = json_decode($body, true);
        if (!is_array($data)) {
            echo json_encode(['ok' => false, 'error' => 'JSON không hợp lệ']);
            break;
        }
        // Đọc config hiện tại để bảo toàn các field không có trong form GUI
        $existing = pf_load_config();

        // ── Helper: clamp số nguyên trong khoảng [min, max] ──────────────────
        $clamp = function($val, $min, $max) use ($existing) {
            return max($min, min($max, (int)$val));
        };

        // ── Validate log_files: chỉ chấp nhận path trong /var/log/ ──────────
        $raw_logs = array_map('trim', (array)($data['log_files'] ?? []));
        $safe_logs = [];
        foreach ($raw_logs as $lf) {
            if ($lf !== '' && strpos(realpath($lf) ?: $lf, '/var/log/') === 0) {
                $safe_logs[] = $lf;
            }
        }
        if (empty($safe_logs)) {
            $safe_logs = $existing['log_files'];  // fallback nếu tất cả bị reject
        }

        $cfg = [
            'telegram_token'          => trim($data['telegram_token'] ?? ''),
            'telegram_chat_id'        => trim($data['telegram_chat_id'] ?? ''),
            'log_files'               => array_values($safe_logs),
            'state_file'              => $existing['state_file'],
            'delay_seconds'           => $clamp($data['delay_seconds']    ?? $existing['delay_seconds'],    0,  60),
            'spam_cooldown'           => $clamp($data['spam_cooldown']     ?? $existing['spam_cooldown'],    0, 3600),
            // Bảo toàn ngưỡng packet loss (không có trong GUI, chỉnh tay trong config.json)
            'high_loss_threshold'     => (int)$existing['high_loss_threshold'],
            'critical_loss_threshold' => (int)$existing['critical_loss_threshold'],
            'gui_fail_threshold'      => $clamp($data['gui_fail_threshold'] ?? $existing['gui_fail_threshold'], 1, 20),
            'retry_count'             => $clamp($data['retry_count']        ?? $existing['retry_count'],        0, 10),
            'retry_backoff'           => $clamp($data['retry_backoff']       ?? $existing['retry_backoff'],      1, 30),
            'rate_limit_per_min'      => $clamp($data['rate_limit_per_min']  ?? $existing['rate_limit_per_min'], 0, 120),
            'use_topics'              => (bool)($data['use_topics'] ?? $existing['use_topics']),
            'topic_name'              => trim($data['topic_name'] ?? $existing['topic_name']),
            'topic_thread_id'         => max(0, (int)($data['topic_thread_id'] ?? $existing['topic_thread_id'])),
        ];
        @mkdir(dirname(PF_CONFIG_FILE), 0750, true);
        $written = file_put_contents(PF_CONFIG_FILE, json_encode($cfg, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
        if ($written === false) {
            echo json_encode(['ok' => false, 'error' => 'Không thể ghi config file']);
        } else {
            @chmod(PF_CONFIG_FILE, 0600);  // Token nhạy cảm — chỉ root đọc được
            echo json_encode(['ok' => true, 'message' => 'Đã lưu config']);
        }
        break;

    case 'test':
        $cfg = pf_load_config();
        if (empty($cfg['telegram_token']) || strpos($cfg['telegram_token'], 'YOUR_BOT') !== false) {
            echo json_encode(['ok' => false, 'error' => 'Chưa cài đặt Telegram Bot Token']);
            break;
        }
        if (empty($cfg['telegram_chat_id'])) {
            echo json_encode(['ok' => false, 'error' => 'Chưa cài đặt Chat ID']);
            break;
        }
        // Gửi test theo log thật để kiểm tra parser/log watcher. Python sẽ tự resolve
        // message_thread_id nếu bật Topics.
        $ret = null;
        @exec(
            PF_PYTHON . ' ' . escapeshellarg(PF_SCRIPT)
            . ' test --config ' . escapeshellarg(PF_CONFIG_FILE) . ' > /dev/null 2>&1',
            $dummy, $ret
        );
        if ($ret === 0) {
            echo json_encode(['ok' => true, 'output' => 'Tin test đã gửi thành công tới Telegram']);
        } else {
            echo json_encode(['ok' => false, 'error' => 'Gửi thất bại — kiểm tra Token và Chat ID']);
        }
        break;

    case 'reset_topic':
        $state_file = '/var/db/pf_notify/state.json';
        $state = [];
        if (file_exists($state_file)) {
            $raw = @json_decode(file_get_contents($state_file), true);
            if (is_array($raw)) $state = $raw;
        }
        unset($state['_topic'], $state['_topic_id']);
        $written = file_put_contents($state_file, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
        if ($written === false) {
            echo json_encode(['ok' => false, 'error' => 'Không thể ghi state file']);
        } else {
            echo json_encode(['ok' => true, 'message' => 'Đã xoá cache topic — lần khởi động tiếp theo sẽ tạo topic mới']);
        }
        break;

    default:
        echo json_encode(['ok' => false, 'error' => 'action không hợp lệ']);
        break;
}
