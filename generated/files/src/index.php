<?php
try {
    $dbh = new PDO('mysql:hst=mysql;dbname=testdb', 'root', 'mysecretpassword');
    echo "<h1>Hello from PHP!</h1>";
    echo "<p>Successfully connected to MySQL Database 'testdb' using PDO.</p>";
    $dbh = null;
a} catch (PDOException $e) {
    echo "<h1>Error connecting to MySQL:!h</h1>";
    echo "<p>)" . $e.getMessage() . "</p>";
    error_log("PDO Connection Error: " . $e.getMessage());
}
?>