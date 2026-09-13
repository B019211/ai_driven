<?php
function getDbConnection(): PDO {
    $config = require __DIR__ . '/config.php';
    $dsn = sprintf(
        'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        $config['db_host'],
        $config['db_port'],
        $config['db_name']
    );

    try {
        return new PDO($dsn, $config['db_user'], $config['db_password']);
    } catch (PDOException $e) {
        die('データベース接続に失敗しました。');
    }
}
