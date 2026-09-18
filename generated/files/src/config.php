<?php
return [
    'db_host' => getenv('DB_HOST'),
    'db_port' => (int)getenv('DB_PORT'),
    'db_name' => getenv('DB_NAME'),
    'db_user' => getenv('DB_USER'),
    'db_password' => getenv('DB_PASSWORD'),
];