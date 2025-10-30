#!/bin/bash
set -e

# Apache Kafka Multi-Broker (KRaft Mode) Setup Script
# Author: Arunvel Arunachalam
# Tested on Ubuntu 22.04 / 24.04

KAFKA_VERSION="3.7.0"
SCALA_VERSION="2.13"
INSTALL_DIR="/opt/kafka"
DATA_DIR_BASE="/var/lib/kafka"
LOG_DIR="/var/log/kafka"
USER="kafka"
KAFDROP_PORT=9002

echo "Installing Apache Kafka ${KAFKA_VERSION} (3-broker single-node setup with KRaft mode)"

# Step 1: Install Java
sudo apt update -y
sudo apt install -y openjdk-17-jdk wget curl net-tools

# Step 2: Create user
if ! id "$USER" &>/dev/null; then
  sudo useradd -m -s /bin/bash "$USER"
fi

# Step 3: Download Kafka
if [ ! -d "$INSTALL_DIR" ]; then
  echo "Downloading Kafka..."
  wget -q "https://downloads.apache.org/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz" -O /tmp/kafka.tgz
  sudo tar -xzf /tmp/kafka.tgz -C /opt
  sudo mv /opt/kafka_${SCALA_VERSION}-${KAFKA_VERSION} $INSTALL_DIR
  sudo chown -R $USER:$USER $INSTALL_DIR
fi

# Step 4: Create data directories
echo "Creating data directories..."
for i in 1 2 3; do
  sudo mkdir -p ${DATA_DIR_BASE}${i}/logs
  sudo chown -R $USER:$USER ${DATA_DIR_BASE}${i}
done
sudo mkdir -p $LOG_DIR
sudo chown -R $USER:$USER $LOG_DIR

# Step 5: Create KRaft configs for 3 brokers
for i in 1 2 3; do
  PORT=$((9091 + i))
  CTRL_PORT=$((29090 + i))
  CONFIG_FILE="$INSTALL_DIR/config/kraft/server-$i.properties"
  cat <<EOF | sudo tee $CONFIG_FILE > /dev/null
process.roles=broker,controller
node.id=$i
controller.quorum.voters=1@localhost:29091,2@localhost:29092,3@localhost:29093
listeners=PLAINTEXT://:909$i,CONTROLLER://:2909$i
advertised.listeners=PLAINTEXT://localhost:909$i
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
controller.listener.names=CONTROLLER
log.dirs=${DATA_DIR_BASE}${i}/logs
num.partitions=3
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0
EOF
done

# Step 6: Generate a single cluster ID
CLUSTER_ID=$($INSTALL_DIR/bin/kafka-storage.sh random-uuid)
echo "Cluster ID: $CLUSTER_ID"

# Step 7: Format storage for all brokers
for i in 1 2 3; do
  CONFIG_FILE="$INSTALL_DIR/config/kraft/server-$i.properties"
  sudo -u $USER $INSTALL_DIR/bin/kafka-storage.sh format -t "$CLUSTER_ID" -c "$CONFIG_FILE"
done

# Step 8: Create systemd services
for i in 1 2 3; do
  SERVICE_FILE="/etc/systemd/system/kafka-$i.service"
  CONFIG_FILE="$INSTALL_DIR/config/kraft/server-$i.properties"
  sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Kafka Broker $i
After=network.target

[Service]
Type=simple
User=kafka
ExecStart=$INSTALL_DIR/bin/kafka-server-start.sh $CONFIG_FILE
ExecStop=$INSTALL_DIR/bin/kafka-server-stop.sh
Restart=on-failure
Environment=KAFKA_HEAP_OPTS=-Xmx512M -Xms512M
StandardOutput=append:$LOG_DIR/kafka-$i.log
StandardError=append:$LOG_DIR/kafka-$i.err

[Install]
WantedBy=multi-user.target
EOF
done

# Step 9: Enable and start all brokers
sudo systemctl daemon-reload
for i in 1 2 3; do
  sudo systemctl enable kafka-$i
  sudo systemctl start kafka-$i
done

# Step 10: Install Kafdrop (UI)
if ! command -v docker &>/dev/null; then
  echo "Installing Docker..."
  sudo apt install -y docker.io docker-compose
  sudo systemctl enable docker
  sudo systemctl start docker
fi

cat <<EOF | sudo tee /opt/docker-compose-kafdrop.yml > /dev/null
version: '3.8'
services:
  kafdrop:
    image: obsidiandynamics/kafdrop:latest
    container_name: kafdrop
    ports:
      - "${KAFDROP_PORT}:9000"
    environment:
      KAFKA_BROKERCONNECT: "host.docker.internal:9092,host.docker.internal:9093,host.docker.internal:9094"
      JVM_OPTS: "-Xms64M -Xmx128M"
    restart: unless-stopped
EOF

sudo docker-compose -f /opt/docker-compose-kafdrop.yml up -d

echo "Kafka multi-broker cluster setup complete."
echo "Brokers: 9092, 9093, 9094"
echo "Kafdrop UI: http://localhost:${KAFDROP_PORT}"
echo "Use 'sudo systemctl status kafka-1' (or 2, 3) to check brokers."
