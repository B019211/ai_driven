<?php
declare(strict_types=1);

// Database configuration from environment variables
$dbHost = getenv('DB_HOST') ?: 'mysql'; // 'mysql' is the service name within the pod
$dbName = getenv('DB_NAME') ?: 'testdb';
$dbUser = getenv('DB_USER') ?: 'app_user';
$dbPassword = getenv('DB_PASSWORD') ?: 'anothersecurepassword'; // IMPORTANT: Use secure methods in production!

$dsn = "mysql:host={$dbHost};dbname={$dbName};charset=utf8mb4";
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

$message = '';
$data = [];

try {
    $pdo = new PDO($dsn, $dbUser, $dbPassword, $options);
    $message = "Successfully connected to MySQL database '{$dbName}'!";

    // Create a simple table if it doesn't exist
    $pdo->exec("CREATE TABLE IF NOT EXISTS messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        content VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )");

    // Insert a message
    $stmt = $pdo->prepare("INSERT INTO messages (content) VALUES (?)");
    $stmt->execute(["Hello from PHP! " . date('Y-m-d H:i:s')]);

    // Fetch messages
    $stmt = $pdo->query("SELECT id, content, created_at FROM messages ORDER BY created_at DESC LIMIT 5");
    $data = $stmt->fetchAll();

} catch (\PDOException $e) {
    $message = "Database connection failed: " . $e->getMessage();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LAMP Pod Application</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        .container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #0056b3; }
        p { margin-bottom: 10px; }
        ul { list-style-type: none; padding: 0; }
        li { background-color: #e9ecef; margin-bottom: 5px; padding: 10px; border-radius: 4px; }
        .error { color: red; font-weight: bold; }
        .success { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>LAMP Pod Application</h1>
        <p class="<?= strpos($message, 'failed') !== false ? 'error' : 'success' ?>">
            <?= htmlspecialchars($message) ?>
        </p>

        <?php if (!empty($data)): ?>
            <h2>Recent Messages:</h2>
            <ul>
                <?php foreach ($data as $row): ?>
                    <li>
                        <strong>ID:</strong> <?= htmlspecialchars((string)$row['id']) ?><br>
                        <strong>Content:</strong> <?= htmlspecialchars($row['content']) ?><br>
                        <strong>Created At:</strong> <?= htmlspecialchars($row['created_at']) ?>
                    </li>
                <?php endforeach; ?>
            </ul>
        <?php endif; ?>
    </div>
</body>
</html>
