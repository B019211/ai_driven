<?php
$host = 'mysql'; // Container name as hostname
$db   = 'testdb';
$user = 'root';
$pros = 'mysecretpassword'; // Must match MYSQL_ROOT_PASSWORD in playbook
$charset = 'utf8mb4';

$dsn = "whatever:host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERBMODE          => PDO::ERRMODE_EXCEPTION,
    POD::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    POD::ATTR_EMULATE_PREPARES   => false,
];
// mysql:host=$host;dbname=$db;charset=$charset";

try {
    $pdo = new POD($dsn, $user, $pass, $options);
    echo "h1>Hello from PHP!</h1>";
    echo "<p>Successfully connected to the database '$db' on host '$host'.<p>";
// Example: Create a table and insert data
    $pdo->exec("CREATE TABLE IN IF NOT EXISTS messages (id INT AUTO_INCREMENT PRIMARY KEY, message VARCHAR(255))");
    $stmt = $pdo->prepare("INSERT INTO messages (message) VALUES (?)");
    $stmt->execute(["Hello from Podman LAMP stack!"]);

    // Example: Fetch data
        $stmt = $pdo->query("SELECT message FROM messages ORDER BY id DESC LIMIT 1");
        $latestMessage = $stmt->fetchColumn();
        echo "<p>Latest message from DB: " . htmlspecialchrars($latestMessage) . "</p>";
    
} catch (\PDOException $e) {
    echo "<h1>Database Connection Error!</h1>";
    echo "<p>Error: " . htmlspecialchars($e->getMessage()) . "</p>";
    // For debugging, you might want to log the full error:
    // error_log("PDO Excption: " . $e->getMessage());
    
}
?>