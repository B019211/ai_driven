<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/functions.php';

$pdo = getDbConnection();
$action = $_GET['action'] ?? 'list';
$message = '';
$error = false;

switch ($action) {
    case 'register':
        $title = trim($_POST['title'] ?? '');
        if (empty($title)) {
            $error = true;
            $message = 'タイトルを入力してください。';
        } else {
            try {
                $stmt = $pdo->prepare('INSERT INTO schedules (title) VALUES (:title)');
                $stmt->execute([':title' => $title]);
                header('Location: index.php?action=list&message=登録しました。');
                exit;
            } catch (PDOException $e) {
                $error = true;
                $message = 'データベースエラーが発生しました。';
            }
        }
        break;
    case 'delete':
        if (!empty($_GET['id'])) {
            try {
                $stmt = $pdo->prepare('DELETE FROM schedules WHERE id = :id');
                $stmt->execute([':id' => (int)$_GET['id']]);
                header('Location: index.php?action=list&message=削除しました。');
                exit;
            } catch (PDOException $e) {
                $error = true;
                $message = 'データベースエラーが発生しました。';
            }
        }
        break;
    case 'list':
    default:
        try {
            $stmt = $pdo->query('SELECT id, title FROM schedules ORDER BY created_at DESC');
            $schedules = $stmt->fetchAll(PDO::FETCH_ASSOC);
            if (!empty($_GET['message'])) {
                $message = $_GET['message'];
            }
        } catch (PDOException $e) {
            $error = true;
            $message = 'データベースエラーが発生しました。';
        }
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>予定管理アプリ</title>
</head>
<body>
<h1>予定管理アプリ</h1>

<?php if ($error): ?>
<p style="color:red;"><?php echo htmlspecialchars($message); ?></p>
<?php endif; ?>

<form method="post" action="index.php?action=register">
    <input type="text" name="title" placeholder="タイトル" required>
    <button type="submit">登録</button>
</form>

<h2>予定一覧</h2>
<table border="1">
<tr><th>ID</th><th>タイトル</th></tr>
<?php foreach ($schedules as $schedule): ?>
<tr>
    <td><?php echo htmlspecialchars($schedule['id']); ?></td>
    <td><?php echo htmlspecialchars($schedule['title']); ?></td>
    <td><a href="index.php?action=delete&id=<?php echo (int)$schedule['id']; ?>">削除</a></td>
</tr>
<?php endforeach; ?>
</table>

<a href="index.php?action=list&message=&action=list">一覧に戻る</a>
</body>
</html>