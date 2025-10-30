import os
import shutil
import subprocess
from flask import Flask, render_template
from flask import request
import string
from flask import request, render_template, redirect, url_for
import docker


client = docker.from_env()


import random
app = Flask(__name__)

def get_os_family():
    if os.path.exists("/etc/debian_version"):
        return "debian"
    elif os.path.exists("/etc/redhat-release"):
        return "redhat"
    else:
        return "unknown"



def install_package(tool, os_family):
    package_map = {
        "docker": "docker.io" if os_family == "debian" else "docker",
        "pip3": "python3-pip",
        "python3-venv": "python3-venv",
        "docker-compose": None  # We'll handle it manually
    }

    package_name = package_map.get(tool, tool)

    try:
        if os_family == "debian":
            subprocess.run(["sudo", "apt", "update"], check=True)

            if tool == "terraform":
                subprocess.run(["sudo", "apt", "install", "-y", "wget", "gnupg", "software-properties-common", "curl"], check=True)
                subprocess.run([
                    "wget", "-O", "hashicorp.gpg", "https://apt.releases.hashicorp.com/gpg"
                ], check=True)
                subprocess.run([
                    "gpg", "--dearmor", "--output", "hashicorp-archive-keyring.gpg", "hashicorp.gpg"
                ], check=True)
                subprocess.run([
                    "sudo", "mv", "hashicorp-archive-keyring.gpg", "/usr/share/keyrings/hashicorp-archive-keyring.gpg"
                ], check=True)

                codename = subprocess.check_output(["lsb_release", "-cs"], text=True).strip()
                apt_line = (
                    f"deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] "
                    f"https://apt.releases.hashicorp.com {codename} main\n"
                )
                with open("hashicorp.list", "w") as f:
                    f.write(apt_line)
                subprocess.run(["sudo", "mv", "hashicorp.list", "/etc/apt/sources.list.d/hashicorp.list"], check=True)

                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "apt", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "apt", "install", "-y", package_name], check=True)

        elif os_family == "redhat":
            if tool == "terraform":
                subprocess.run(["sudo", "yum", "install", "-y", "yum-utils"], check=True)
                subprocess.run([
                    "sudo", "yum-config-manager", "--add-repo",
                    "https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo"
                ], check=True)
                subprocess.run(["sudo", "yum", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "yum", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "yum", "install", "-y", package_name], check=True)

        else:
            return False, "Unsupported OS"

        return True, None

    except Exception as e:
        return False, str(e)




@app.route("/pre-req")
def prereq():
    tools = ["pip3", "openssl", "docker","docker-compose"]
    results = {}
    os_family = get_os_family()

    for tool in tools:
        if shutil.which(tool):
            results[tool] = "✅ Installed"
        else:
            success, error = install_package(tool, os_family)
            if success:
                results[tool] = "❌ Not Found → 🛠️ Installed"
            else:
                results[tool] = f"❌ Not Found → ❌ Error: {error}"



    docker_installed = shutil.which("docker") is not None
    return render_template("prereq.html", results=results, os_family=os_family, docker_installed=docker_installed)












# Check if Portainer is actually installed and running (or exists as a container)
def is_portainer_installed():
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "portainer"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip() in ["true", "false"]
    except Exception:
        return False

# Actually run Portainer
def run_portainer():
    try:
        subprocess.run(["docker", "volume", "create", "portainer_data"], check=True)
        subprocess.run([
            "docker", "run", "-d",
            "-p", "9443:9443", "-p", "9000:9000",
            "--name", "portainer",
            "--restart=always",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", "portainer_data:/data",
            "portainer/portainer-ce:latest"
        ], check=True)
        return True, "✅ Portainer installed successfully."
    except subprocess.CalledProcessError as e:
        return False, f"❌ Docker Error: {str(e)}"

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/install_portainer", methods=["GET", "POST"])
def install_portainer_route():
    installed = is_portainer_installed()
    portainer_url = "https://localhost:9443"
    message = None

    if request.method == "POST":
        if not installed:
            success, message = run_portainer()
            installed = success
        else:
            message = "ℹ️ Portainer is already installed."

    return render_template("portainer.html", installed=installed, message=message, url=portainer_url)




##################KAFKA INSTALLATION##################

@app.route("/kafka")
def linux_info():
    return render_template("kafka_info.html")

########################### kafka cluster setup = start #################################


import os
import random

used_ports = set()

def get_random_port(start=4000, end=9000):
    while True:
        port = random.randint(start, end)
        if port not in used_ports:
            used_ports.add(port)
            return port


def create_kafka_compose_file(version, container_name):
    import os
    os.makedirs("compose_files", exist_ok=True)
    os.makedirs("kafka_clusters", exist_ok=True)

    cluster_dir = f"./kafka_clusters/{container_name}"
    os.makedirs(cluster_dir, exist_ok=True)

    # Ports
    zk_port = get_random_port()
    broker_ports = [get_random_port() for _ in range(3)]
    kafdrop_port = get_random_port()

    compose_content = f"""
version: '3.8'
services:
  kafka-1:
    image: apache/kafka:latest
    container_name: {container_name}-1
    hostname: {container_name}-1
    ports:
      - {broker_ports[0]}:9092
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@{container_name}-1:29093,2@{container_name}-2:29093,3@{container_name}-3:29093
      KAFKA_LISTENERS: PLAINTEXT://{container_name}-1:9092,CONTROLLER://{container_name}-1:29093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://{container_name}-1:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
    networks:
      - kafka-net

  kafka-2:
    image: apache/kafka:latest
    container_name: {container_name}-2
    hostname: {container_name}-2
    ports:
      - {broker_ports[1]}:9093
    environment:
      KAFKA_NODE_ID: 2
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@{container_name}-1:29093,2@{container_name}-2:29093,3@{container_name}-3:29093
      KAFKA_LISTENERS: PLAINTEXT://{container_name}-2:9093,CONTROLLER://{container_name}-2:29093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://{container_name}-2:9093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
    networks:
      - kafka-net

  kafka-3:
    image: apache/kafka:latest
    container_name: {container_name}-3
    hostname: {container_name}-3
    ports:
      - {broker_ports[2]}:9094
    environment:
      KAFKA_NODE_ID: 3
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@{container_name}-1:29093,2@{container_name}-2:29093,3@{container_name}-3:29093
      KAFKA_LISTENERS: PLAINTEXT://{container_name}-3:9094,CONTROLLER://{container_name}-3:29093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://{container_name}-3:9094
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
    networks:
      - kafka-net

  kafdrop:
    image: obsidiandynamics/kafdrop:latest
    container_name: {container_name}-ui
    ports:
      - {kafdrop_port}:9000
    environment:
      KAFKA_BROKERCONNECT: "{container_name}-1:9092,{container_name}-2:9093,{container_name}-3:9094"
      SERVER_PORT: 9000
    depends_on:
      - kafka-1
      - kafka-2
      - kafka-3
    networks:
      - kafka-net

networks:
  kafka-net:
    driver: bridge
"""

    file_path = os.path.join(cluster_dir, "docker-compose.yml")
    with open(file_path, "w") as f:
        f.write(compose_content)

    # ✅ FIX: Return all 4 values
    return file_path, zk_port, broker_ports, kafdrop_port

########################### kafka cluster setup = end #################################




@app.route("/kafka/clusters")
def kafka_clusters():
    """
    List all running Kafka containers based on image name (not container name).
    """
    containers = client.containers.list()
    kafka_containers = []

    for container in containers:
        image_name = container.image.tags[0] if container.image.tags else ""
        if "kafka" in image_name.lower():  # <-- match by image name
            info = {
                "name": container.name,
                "status": container.status,
                "image": image_name,
                "ip": container.attrs['NetworkSettings']['IPAddress']
            }
            kafka_containers.append(info)

    return render_template("kafka_clusters.html", clusters=kafka_containers)


########################################################################################################################

def run_docker_compose(compose_file, container_name):
    try:
        subprocess.run(["docker-compose", "-p", container_name, "-f", compose_file, "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to run Docker Compose: {e}")
        raise

# Routes



@app.route("/kafka/setup", methods=["GET", "POST"])
def kafka_setup():
    if request.method == "POST":
        version = request.form["version"]  # e.g. 2.13-3.6.1
        name = request.form["name"].strip()  # e.g. student1-kafka

        # create the docker-compose file for this student
        file_path, zk_port, broker_ports, kafdrop_port = create_kafka_compose_file(version, name)

        # run the docker-compose up command
        run_docker_compose(file_path, name)

        return render_template(
            "success.html",
            os_type="Kafka Cluster",
            version=version,
            container=name,
            rdp=None,
            web=f"http://localhost:{kafdrop_port}"  # Link to Kafdrop UI
        )

    # if GET request → show form for cluster name + version
    return render_template("kafka_setup.html")








if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=True)
