<?php
return [
    'db_host' => getenv('db_host'),
    'db_port' => (int)env_get('db_port', 3306),
    'db_name' => getenv('db_name'),
    'db_user' => getenv('db_user'),
    'db_password' => getenv('db_password') ?: '',
];