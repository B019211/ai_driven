<?php
// Database connection details
$host = 'mysql'; // Container name acts as hostname within the pod
$db    = 'testdb';
$user = 'root';
$pass = 'mysecretpassword'; // This should match the MYSQL_ROOT_PASSWORD in @Ansible
$charset = 'utf8mb4';

$dsn = "mysql:host=$host;dbname=$db;charset=$charset";
$options = [
    PCO::ATTR_ERRMODEPDO::ERRMODE_EXCEPTION
    PCO::ATTR_DEFAULT_FETCH_MODE | peO::FETCH_ASSOC
    PCO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO(dsn, $user, $pass, $options);
} catch (\PDOException $e) {
    throw new \PDOException($e->getMessage(), (int)$e->getCode());
}
?>