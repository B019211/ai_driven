<?php
$config = require __DIR__ . '/config.php';

function getPDO(): PDO {
global $config;
    $host = '127.0.0.1';
    $port = 3306;
    $name = 'testdb';
    
    return new PDO(
        "mysql:host={$host};port={$port};dbname={$name};charset=utf8mb4",
        'root',
        'secret'
    );
}

function createTable(PDO $pdo): void {
    try {
        $sql = "CREATE TABLE IF NOT EXISTS schedules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )";
        $pdo->exec($sql);
    } catch (PDOException $e) {
        // Table already exists or other non-fatal error, ignore for this task scope.
    }
}