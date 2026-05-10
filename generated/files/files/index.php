<?php

$host = 'mysql'; // Container name within the pod
$db   = 'testdb';
$user = 'lampuser';
$pass = 'lamp_password'; // Must match the Ansible variable
$charset = 'utf8mb4';

$dsn = "mysql:host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $user, $pass, $options);
    echo "<h1>Connected to MySQL successfully!</h1>";

    // Create a simple table if it doesn't exist
    $pdo->exec("CREATE TABLE IF NOT EXISTS messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        message VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )");
    echo "<p>Table 'messages' ensured.</p>";

    // Insert a message
    $stmt = $pdo->prepare("INSERT INTO messages (message) VALUES (?)");
    $stmt->execute(["Hello from PHP " . phpversion() . " at " . date('Y-m-d H:i:s')]);
    echo "<p>Message inserted.</p>";

    // Select and display messages
    $stmt = $pdo->query("SELECT id, message, created_at FROM messages ORDER BY created_at DESC LIMIT 5");
    $messages = $stmt->fetchAll();

    echo "<h2>Recent Messages:</h2>";
    if (count($messages) > 0) {
        echo "<ul>";
        foreach ($messages as $message) {
            echo "<li>ID: " . htmlspecialchars($message['id']) . ", Message: " . htmlspecialchars($message['message']) . " (" . htmlspecialchars($message['created_at']) . ")</li>";
        }
        echo "</ul>";
    } else {
        echo "<p>No messages found.</p>";
    }

} catch (PDOException $e) {
    error_log("Database connection failed: " . $e->getMessage());
    echo "<h1>Database connection failed. Please check the configuration.</h1>";
    // In a production environment, avoid exposing detailed error messages to users
    // throw new PDOException($e->getMessage(), (int)$e->getCode());
}

?>
