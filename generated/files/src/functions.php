<?php
require_once __DIR__ . '/db.php';

function getSchedules(PDO $pdo): array {
    try {
        $stmt = $pdo->query('SELECT id, title, description FROM schedules ORDER BY created_at DESC');
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $e) {
        throw new RuntimeException('Failed to fetch schedules: ' . $e->getMessage());
    }
}

function createSchedule(PDO $pdo, string $title, ?string $description = null): int {
    try {
        $stmt = $pdo->prepare(
            "INSERT INTO schedules (title, description) VALUES (:title, :description)"
        );
        $stmt->execute([
            ':title' => $title,
            ':description' => $description
        ]);
        return (int)$stmt->lastInsertId();
    } catch (PDOException $e) {
        throw new RuntimeException('Failed to create schedule: ' . $e->getMessage());
    }
}

function deleteSchedule(PDO $pdo, int $id): bool {
    try {
        $stmt = $pdo->prepare("DELETE FROM schedules WHERE id = :id");
        return (bool)$stmt->execute([':id' => $id]);
    } catch (PDOException $e) {
        throw new RuntimeException('Failed to delete schedule: ' . $e->getMessage());
    }
}
