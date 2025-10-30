#!/bin/bash
set -e


KAFKA_VERSION="4.0.1"
SCALA_VERSION="2.13"
INSTALL_DIR="/opt/kafka"
DATA_DIR="/var/lib/kafka"
LOG_DIR="/var/log/kafka"
USER="kafka"
SERVICE_FILE="/etc/systemd/system/kafka.service"
KAFDROP_PORT=9002

echo "Installing Apache Kafka ${KAFKA_VERSION} (KRaft Mode) with Kafdrop UI"

# Step 1: Install Java and required tools
echo "Installing Java and tools..."
sudo apt update -y
sudo apt install -y openjdk-17-jdk curl wget net-tools unzip

# Step 2: Install Docker and Docker Compose (for Kafdrop)
if ! command -v docker &>/dev/null; then
  echo "Installing Docker..."
  sudo apt install -y ca-certificates curl gnupg lsb-release
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt update -y
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable docker
  sudo systemctl start docker
fi

if ! command -v docker-compose &>/dev/null; then
  echo "Installing docker-compose..."
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
fi

# Step 3: Create Kafka user
if ! id "$USER" &>/dev/null; then
  echo "Creating kafka user..."
  sudo useradd -m -s /bin/bash "$USER"
fi

# Step 4: Download Kafka
echo "Downloading Kafka..."
cd /tmp
wget -q "https://downloads.apache.org/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz"

echo "Extracting Kafka..."
sudo tar -xzf "kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz" -C /opt
sudo mv "/opt/kafka_${SCALA_VERSION}-${KAFKA_VERSION}" "$INSTALL_DIR"

# Step 5: Setup directories
echo "Setting up directories..."
sudo mkdir -p "$DATA_DIR" "$LOG_DIR"
sudo chown -R $USER:$USER "$INSTALL_DIR" "$DATA_DIR" "$LOG_DIR"

# Step 6: Configure Kafka (KRaft)
CONFIG_FILE="$INSTALL_DIR/config/kraft/server.properties"
cat <<EOF | sudo tee $CONFIG_FILE > /dev/null
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:29093
listeners=PLAINTEXT://:9092,CONTROLLER://:29093
advertised.listeners=PLAINTEXT://localhost:9092
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
controller.listener.names=CONTROLLER
log.dirs=$DATA_DIR/logs
num.partitions=3
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0
EOF

# Step 7: Format KRaft storage
echo "Formatting KRaft storage..."
CLUSTER_ID=$("$INSTALL_DIR"/bin/kafka-storage.sh random-uuid)
sudo -u $USER "$INSTALL_DIR"/bin/kafka-storage.sh format \
  -t "$CLUSTER_ID" \
  -c "$CONFIG_FILE"

# Step 8: Create systemd service
echo "Creating systemd service..."
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Apache Kafka Server (KRaft Mode)
After=network.target

[Service]
Type=simple
User=kafka
ExecStart=$INSTALL_DIR/bin/kafka-server-start.sh $CONFIG_FILE
ExecStop=$INSTALL_DIR/bin/kafka-server-stop.sh
Restart=on-failure
Environment=KAFKA_HEAP_OPTS=-Xmx1G -Xms1G
StandardOutput=append:$LOG_DIR/kafka.log
StandardError=append:$LOG_DIR/kafka.err

[Install]
WantedBy=multi-user.target
EOF

# Step 9: Start Kafka service
echo "Starting Kafka..."
sudo systemctl daemon-reload
sudo systemctl enable kafka
sudo systemctl start kafka

# Step 10: Setup Kafdrop
echo "Deploying Kafdrop (UI) via Docker..."
cat <<EOF | sudo tee /opt/docker-compose-kafdrop.yml > /dev/null
version: '3.8'
services:
  kafdrop:
    image: obsidiandynamics/kafdrop:latest
    container_name: kafdrop
    ports:
      - "${KAFDROP_PORT}:9000"
    environment:
      KAFKA_BROKERCONNECT: "host.docker.internal:9092"
      JVM_OPTS: "-Xms64M -Xmx128M"
    restart: unless-stopped
EOF

sudo docker-compose -f /opt/docker-compose-kafdrop.yml up -d

echo "Kafka and Kafdrop installation completed successfully."
echo "Kafka is running in KRaft mode on port 9092."
echo "Kafdrop UI is accessible at: http://localhost:${KAFDROP_PORT}"
echo "Use 'sudo systemctl status kafka' to check Kafka service."
