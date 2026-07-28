import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ai_pipeline import (
    analyze_browser_validation,
    analyze_php_lint_result,
    extract_file_content_from_response,
    repair_podman_yaml_content,
)


class PodmanRepairTests(unittest.TestCase):
    def test_container_publish_is_moved_to_pod_publish(self) -> None:
        content = """---
- name: Create pod
  hosts: execution
  tasks:
    - name: Create lamp-pod
      containers.podman.podman_pod:
        name: lamp-pod
        state: started
    - name: Create PHP container
      containers.podman.podman_container:
        name: php
        image: php:8.2-apache
        pod: lamp-pod
        publish:
          - "8080:80"
        env:
          FOO: bar
"""

        repaired = repair_podman_yaml_content(content)
        parsed = yaml.safe_load(repaired)

        self.assertIsInstance(parsed, list)
        pod_config = parsed[0]["tasks"][0]["containers.podman.podman_pod"]
        container_config = parsed[0]["tasks"][1]["containers.podman.podman_container"]

        self.assertEqual(pod_config["publish"], ["8080:80"])
        self.assertNotIn("publish", container_config)

    def test_extract_file_content_from_json_response(self) -> None:
        response = '{"summary": "ok", "files": [{"path": "ansible/playbook.yml", "content": "- hosts: all\n"}]}'
        extracted = extract_file_content_from_response(response)
        self.assertEqual(extracted, "- hosts: all")

    def test_browser_validation_detects_failed_status(self) -> None:
        issues = analyze_browser_validation({"status": 500, "body": "Fatal error", "headers": {"Content-Type": "text/html"}})
        self.assertTrue(any(issue["type"] == "browser_status" for issue in issues))

    def test_php_lint_detects_parse_error(self) -> None:
        issues = analyze_php_lint_result({"exit_code": 1, "stdout": "Parse error\nUnexpected ;", "stderr": ""})
        self.assertTrue(any(issue["type"] == "php_lint" for issue in issues))

    def test_env_list_is_normalized_to_dict(self) -> None:
        content = """---
- name: Create pod
  hosts: execution
  tasks:
    - name: Create PHP container
      containers.podman.podman_container:
        name: php
        image: php:8.2-apache
        env:
          - DOCUMENT_ROOT=/var/www/html
"""

        repaired = repair_podman_yaml_content(content)
        parsed = yaml.safe_load(repaired)
        container_config = parsed[0]["tasks"][0]["containers.podman.podman_container"]

        self.assertEqual(container_config["env"], {"DOCUMENT_ROOT": "/var/www/html"})


if __name__ == "__main__":
    unittest.main()
