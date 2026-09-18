<?php
require_once __DIR__ . '/functions.php';

try {
    $pdo = getPDO();
    createTable($pdo);
} catch (Exception $e) {
    die('Database connection failed: ' . htmlspecialchars($e->getMessage()));
}

$schedules = getSchedules($pdo);
?>
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>予定管理アプリ</title>
</head>
<body>
<h1>予定一覧</h1>

<form method="post" action="#add-form">
    <input type="hidden" name="action" value="create">
    <label for="new-title">タイトル:</label><br>
    <input type="text" id="new-title" name="title" required style="width: 300px;"><br><br>
    <label for="new-desc">説明 (任意):</label><br>
    <textarea id="new-desc" name="description"></textarea><br><br>
    <button type="submit">登録する</button>
</form>

<hr>

<?php if ($schedules === []): ?>
<p>予定がありません。</p>
<?php else: ?>
<table border="1" cellpadding="5">
    <tr>
        <th>ID</th>
        <th>タイトル</th>
        <th>説明</th>
        <th>操作</th>
    </tr>
    <?php foreach ($schedules as $schedule): ?>
    <tr>
        <td><?php echo htmlspecialchars($schedule['id']); ?></td>
        <td><?php echo htmlspecialchars($schedule['title']); ?></td>
        <td><?php echo htmlspecialchars($schedule['description'] ?? ''); ?></td>
        <td><a href="#delete-form-<?php echo $schedule['id']; ?>">削除</a></td>
    </tr>
    <?php endforeach; ?>
</table>
<?php endif; ?>

<form id="add-form" method="post">
    <input type="hidden" name="action" value="create">
    <label for="title">タイトル:</label><br>
    <input type="text" id="title" name="title" required style="width: 300px;"><br><br>
    <label for="description">説明 (任意):</label><br>
    <textarea id="description" name="description"></textarea><br><br>
    <button type="submit">登録する</button>
</form>

<?php foreach ($schedules as $schedule): ?>
<form method="post" style="display:none;" id="delete-form-<?php echo $schedule['id']; ?>">
    <input type="hidden" name="action" value="delete">
    <input type="hidden" name="id" value="<?php echo htmlspecialchars($schedule['id']); ?>">
</form>
<script>
document.getElementById('delete-form-<?php echo $schedule['id']; ?>'.replace(/#/g, '')).addEventListener('submit', function(e) {
    e.preventDefault();
    if(confirm('この予定を削除しますか？')) {
        this.submit();
    }
});
</script>
<?php endforeach; ?>

</body>
</html>