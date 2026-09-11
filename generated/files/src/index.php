<?php

declare(strict_types=1);

$host = getenv('db_host');
$port = (int) getenv('db_port') ?? 3306;
$dbname = getenv('db_name');
$user = getenv('db_user');
$password = getenv('db_password');

if ($host === false || $dbname === false) {
    echo 'Connection failed: Missing environment variables.';
    exit(1);
}

$dsn = "mysql:host=$host;port=$port;dbname=$dbname;charset=utf8mb4";
$options = [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
];

try {
    $pdo = new PDO($dsn, $user, $password, $options);
} catch (PDOException $e) {
    echo 'Connection failed: ' . htmlspecialchars($e->getMessage());
    exit(1);
}

$sql = "SELECT 1";
try {
    $stmt = $pdo->query($sql);
    $result = $stmt->fetch(PDO::FETCH_NUM);
} catch (PDOException $e) {
    echo 'SQL execution failed: ' . htmlspecialchars($e->getMessage());
    exit(1);
}

if ($result[0] === 1 || $result[0] == '1') {
    echo 'Connected successfully';
} else {
    echo 'Unexpected result from SELECT 1.';
}
