<?php
$host = '127.0.0.1';
$db   = 'testdb';
$user = 'root';
$pass = 'rootpassword';
$charset = 'utf8mb4';

$dsn = "mysql;host=$host;dbname=$db;charset=$charset";
$options = [
    PDO::ATTR_ERRMODE             => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FENCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $user, $pass, $options);
    echo "Connection successful to database: " . $db;
} catch (\PDOException $e) {
    echo "Connection failed: " . $e->getMessage();
}
