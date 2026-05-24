{
  "summary": "AI DevOpsアーキテクチャの改善として、Podmanを使用したLAMPスタックの完全なデプロイメントフローをAnsibleで自動化しました。ウェブサーバー（PHP/Apache）とデータベース（MySQL）を単一のPodman Pod内でコンテナ化し、永続的なデータボリュームを設定しています。また、PDOを使用してデータベースに接続し、データの挿入と取得を行うシンプルなPHPアプリケーションを含め、システムの動作検証を可能にしました。",
  "files": [
    {
      "path": "ansible/inventory.ini",
      "content": "[all]\nasbsvr\n\n[rockey8]\nrockey8 ansible_host=rockey8 ansible_user=vboxuser"
    },
    {
      "path": "ansible/playbook.yml",
      "content": "---\n- name: Deploy LAMP stack with Podman\n  hosts: rockey8\n  become: yes\n  vars:\n    mysql_root_password: \"mysecurepassword\" # 本番環境ではAnsible Vaultなどで管理することを強く推奨\n    mysql_user_password: \"anothersecurepassword\" # 本番環境ではAnsible Vaultなどで管理することを強く推奨\n    html_dir: /home/vboxuser/containers/html\n    mysql_data_dir: /home/vboxuser/containers/mysql-data\n    kube_yaml_path: /tmp/lamp-pod.yaml\n\n  tasks:\n    - name: Ensure Podman is installed\n      package:\n        name: podman\n        state: present\n\n    - name: Create html content directory\n      file:\n        path: \"{{ html_dir }}\"\n        state: directory\n        mode: '0755'\n        owner: vboxuser\n        group: vboxuser\n\n    - name: Create mysql data directory\n      file:\n        path: \"{{ mysql_data_dir }}\"\n        state: directory\n        mode: '0755'\n        owner: vboxuser\n        group: vboxuser\n\n    - name: Copy index.php to html directory\n      template:\n        src: ../html/index.php.j2\n        dest: \"{{ html_dir }}/index.php\"\n        mode: '0644'\n        owner: vboxuser\n        group: vboxuser\n\n    - name: Generate Podman Kube YAML\n      template:\n        src: templates/podman-lamp-pod.yaml.j2\n        dest: \"{{ kube_yaml_path }}\"\n\n    - name: Deploy lamp-pod using podman play kube\n      command: podman play kube \"{{ kube_yaml_path }}\"\n      register: podman_play_output\n      changed_when: \"'Created pod' in podman_play_output.stdout or 'Created container' in podman_play_output.stdout or 'Successfully pulled image' in podman_play_output.stdout\"\n\n    - name: Ensure lamp-pod is running\n      command: podman ps --filter \"name=lamp-pod\" --format \"{{ '{{ .Status }}' }}\"\n      register: pod_status\n      until: \"'Up' in pod_status.stdout\"\n      retries: 10\n      delay: 5\n\n    - name: Clean up temporary kube YAML\n      file:\n        path: \"{{ kube_yaml_path }}\"\n        state: absent\n"
    },
    {
      "path": "ansible/templates/podman-lamp-pod.yaml.j2",
      "content": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: lamp-pod\nspec:\n  containers:\n    - name: web\n      image: php:8.2-apache\n      ports:\n        - containerPort: 80\n          hostPort: 8080\n      volumeMounts:\n        - name: html-volume\n          mountPath: /var/www/html\n      env:\n        - name: APACHE_RUN_USER\n          value: \"www-data\"\n        - name: APACHE_RUN_GROUP\n          value: \"www-data\"\n    - name: mysql\n      image: mysql:8.0\n      env:\n        - name: MYSQL_ROOT_PASSWORD\n          value: \"{{ mysql_root_password }}\"\n        - name: MYSQL_DATABASE\n          value: testdb\n        - name: MYSQL_USER\n          value: testuser\n        - name: MYSQL_PASSWORD\n          value: \"{{ mysql_user_password }}\"\n      volumeMounts:\n        - name: mysql-data-volume\n          mountPath: /var/lib/mysql\n  volumes:\n    - name: html-volume\n      hostPath:\n        path: /home/vboxuser/containers/html\n        type: DirectoryOrCreate\n    - name: mysql-data-volume\n      hostPath:\n        path: /home/vboxuser/containers/mysql-data\n        type: DirectoryOrCreate\n"
    },
    {
      "path": "html/index.php.j2",
      "content": "<?php\n$servername = \"localhost\"; // mysql container hostname within the pod\n$username = \"testuser\";\n$password = \"{{ mysql_user_password }}\"; // Ansible variable\n$dbname = \"testdb\";\n\ntry {\n    $conn = new PDO(\"mysql:host=$servername;dbname=$dbname\", $username, $password);\n    // Set the PDO error mode to exception\n    $conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);\n    echo \"<h1>Connected successfully to MySQL!</h1>\";\n\n    // Create a simple table if it doesn't exist\n    $sql_create_table = \"CREATE TABLE IF NOT EXISTS messages (\n        id INT(6) UNSIGNED AUTO_INCREMENT PRIMARY KEY,\n        message VARCHAR(255) NOT NULL,\n        reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP\n    )\";\n    $conn->exec($sql_create_table);\n    echo \"<p>Table 'messages' checked/created successfully.</p>\";\n\n    // Insert a message\n    $message = \"Hello from PHP container!\";\n    $stmt = $conn->prepare(\"INSERT INTO messages (message) VALUES (:message)\");\n    $stmt->bindParam(':message', $message);\n    $stmt->execute();\n    echo \"<p>New record created successfully.</p>\";\n\n    // Retrieve and display messages\n    $stmt = $conn->query(\"SELECT id, message, reg_date FROM messages\");\n    echo \"<h2>Messages:</h2>\";\n    echo \"<ul>\";\n    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {\n        echo \"<li>ID: \" . $row['id'] . \" - Message: \" . $row['message'] . \" - Date: \" . $row['reg_date'] . \"</li>\";\n    }\n    echo \"</ul>\";\n\n} catch(PDOException $e) {\n    echo \"<h1>Connection failed:</h1> \" . $e->getMessage();\n}\n?>\n"
    }
  ],
  "commands": [
    "ssh vboxuser@asbsvr",
    "cd /path/to/ansible/directory",
    "ansible-playbook -i inventory.ini playbook.yml",
    "ssh vboxuser@rockey8",
    "podman ps",
    "podman logs lamp-pod-web",
    "curl localhost:8080"
  ],
  "risks": [
    "MySQLのrootおよびユーザーパスワードがAnsibleのプレイブックにハードコードされています。本番環境では、Ansible Vaultや専用のシークレット管理システムを使用して、これらの機密情報を安全に管理する必要があります。",
    "Podman Play Kubeは一般的に冪等性がありますが、Pod定義に対する抜本的な変更（例: ボリュームパスの変更、ポートの変更など）は、既存のPodを手動で停止・削除しないと適切に適用されない可能性があります。現在の実装では既存Podの強制削除は行っていません。",
    "コンテナのリソース制限（CPU, メモリ）が設定されていません。これにより、リソース枯渇やパフォーマンスの問題が発生する可能性があります。",
    "コンテナのログ収集や監視のための集中型ソリューションは含まれていません。問題発生時のトラブルシューティングが困難になる可能性があります。",
    "Execution Node (rockey8) のファイアウォールがPodmanによって公開されるポート8080へのアクセスを許可している必要があります。",
    "Ansibleの実行ユーザー (vboxuser) がrockey8上でPodmanの実行とディレクトリ作成に必要なsudo権限を持っている必要があります。"
  ]
}