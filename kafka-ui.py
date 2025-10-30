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
    tools = ["pip3", "openssl", "docker", "terraform","docker-compose"]
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
  zookeeper:
    image: bitnami/zookeeper:3.9
    container_name: {container_name}-zookeeper
    ports:
      - "{zk_port}:2181"
    restart: always

  kafka1:
    image: bitnami/kafka:{version}    
    container_name: {container_name}-broker1
    ports:
      - "{broker_ports[0]}:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:{broker_ports[0]}
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    depends_on:
      - zookeeper
    restart: always

  kafka2:
    image: bitnami/kafka:{version} 
    container_name: {container_name}-broker2
    ports:
      - "{broker_ports[1]}:9092"
    environment:
      KAFKA_BROKER_ID: 2
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:{broker_ports[1]}
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    depends_on:
      - zookeeper
    restart: always

  kafka3:
    image: bitnami/kafka:{version} 
    container_name: {container_name}-broker3
    ports:
      - "{broker_ports[2]}:9092"
    environment:
      KAFKA_BROKER_ID: 3
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:{broker_ports[2]}
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    depends_on:
      - zookeeper
    restart: always

  kafdrop:
    image: obsidiandynamics/kafdrop
    container_name: {container_name}-ui
    environment:
      KAFKA_BROKERCONNECT: "kafka1:9092,kafka2:9092,kafka3:9092"
      JVM_OPTS: "-Xms32M -Xmx64M"
    ports:
      - "{kafdrop_port}:9000"
    depends_on:
      - kafka1
      - kafka2
      - kafka3
    restart: always
"""

    file_path = f"compose_files/{container_name}.yml"
    with open(file_path, "w") as f:
        f.write(compose_content)

    return file_path, zk_port, broker_ports, kafdrop_port

########################### kafka cluster setup = end #################################







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



@app.route("/linux/desktop", methods=["GET", "POST"])
def linux_desktop():
    if request.method == "POST":
        version = request.form["version"]  # e.g. ubuntudesktop
        name = request.form["name"].strip() or generate_random_name("linuxdesk")
        path, container, ssh_port = create_linux_compose_file(version, name)
        run_docker_compose(path, container)
        return render_template("success.html", os_type="Linux Desktop", version=version, container=container, rdp=ssh_port, web=None)
    return render_template("linux_desktop.html")


@app.route("/linux/server/install/<version>")
def install_linux_server(version):
    name = generate_random_name("linuxsrv")
    path, container, ssh_port = create_linux_compose_file(version, name)
    run_docker_compose(path, container)
    return render_template("success.html", os_type="Linux Server", version=version, container=container, rdp=ssh_port, web=None)

@app.route("/linux/desktop/install/<version>")
def install_linux_desktop(version):
    name = generate_random_name("linuxdesk")
    path, container, ssh_port = create_linux_compose_file(version, name)
    run_docker_compose(path, container)
    return render_template("success.html", os_type="Linux Desktop", version=version, container=container, rdp=ssh_port, web=None)


@app.route("/linux/server/server_list")
def list_linux_servers():
    containers = []
    for c in client.containers.list():
        try:
            if c.image.tags and (
                c.image.tags[0].startswith("redhat/ubi") or 
                "arunvel1988/rhel" in c.image.tags[0]
            ):
                version = c.image.tags[0].split(":")[0].split("/")[-1]
                containers.append({
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0],
                    "version": version,
                    "ports": ", ".join([
                        f"{container_port}->{details[0]['HostPort']}"
                        for container_port, details in (c.attrs['NetworkSettings']['Ports'] or {}).items()
                        if details
                    ])
                })
        except Exception as e:
            print(f"[!] Skipped container {c.name} due to error: {e}")
    return render_template("list.html", os_type="Linux Server", containers=containers)


@app.route("/linux/desktop/desktop_list")
def list_linux_desktops():
    containers = []
    for c in client.containers.list():
        try:
            if c.image.tags and "ubuntu" in c.image.tags[0]:
                version = c.image.tags[0].split(":")[0].split("/")[-1]
                containers.append({
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0],
                    "version": version,
                    "ports": ", ".join([
                        f"{container_port}->{details[0]['HostPort']}"
                        for container_port, details in (c.attrs['NetworkSettings']['Ports'] or {}).items()
                        if details
                    ])
                })
        except Exception as e:
            print(f"[!] Skipped container {c.name} due to error: {e}")
    return render_template("list.html", os_type="Linux Desktop", containers=containers)




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=True)
