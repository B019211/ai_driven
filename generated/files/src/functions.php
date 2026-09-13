<?php
function env_get(string $name, mixed $default = null): mixed {
    return getenv($name) ?: $default;
}