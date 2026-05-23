-- Create the testdb database if it doesn't exist
CREATE DATABASE IF NOT EXISTS testdb;

-- Use the testdb database
USE testdb;

-- Create a table for messages if it doesn't exist
CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert some initial data
INSERT INTO messages (message) VALUES ('Hello from the LAMP pod!');
INSERT INTO messages (message) VALUES ('This is an initial message.');
