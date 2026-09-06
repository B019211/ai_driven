<?php
// Retrieve database connection values from environment variables using getenv()
$db_host = getenv('db_host');
$db_port = intval(getenv('db_port'));
$db_name = getenv('db_name');
$db_user = getenv('db_user');
$db_password = getenv('db_password');

// Validate that required environment variables are set
if (!$db_host || !$db_port || !$db_name || !$db_user || !$db_password) {
    http_response_code(500);
    echo "Error: Missing required environment variables (db_host, db_port, db_name, db_user, db_password).";
    exit;
}

// Construct the DSN for PDO
$dsn = "mysql:host=$db_host;port=$db_port;dbname=$db_name;charsets=utf8mb4";

// Create PDO connection
try {
    $pdo = new PDO($dsn, $db_user, $db_password, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
    ]);

    // Execute SELECT 1
    $result = $pdo->query('SELECT 1');
    $row = $result->fetch();

    // Display success message
    echo "Connected successfully\n";
    echo "SQL Result: " . $row[0] . "\n";

} catch (PDOException $e) {
    // Display error if connection or query fails
    http_response_code(500);
    echo "Database error: " . $e->getMessage() . "\n";
}
?>