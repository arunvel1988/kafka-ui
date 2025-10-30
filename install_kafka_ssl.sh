#!/bin/bash
set -e

KAFKA_VERSION="3.7.0"
SCALA_VERSION="2.13"
INSTALL_DIR="/opt/kafka"
DATA_DIR_BASE="/var/lib/kafka"
LOG_DIR="/var/log/kafka"
USER="kafka"
SSL_DIR="/etc/kafka/ssl"
KAFDROP_PORT=9002

echo "Installing Kafka with SSL (3-broker single-node KRaft cluster)"

sudo apt update -y
sudo apt install -y openjdk-17-jdk wget openssl docker.io docker-compose -y

# Create user if missing
id $USER &>/dev/null || sudo useradd -m -s /bin/bash $USER

# Download Kafka if not exists
if [ ! -d "$INSTALL_DIR" ]; then
  wget -q "https://downloads.apache.org/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz" -O /tmp/kafka.tgz
  sudo tar -xzf /tmp/kafka.tgz -C /opt
  sudo mv /opt/kafka_${SCALA_VERSION}-${KAFKA_VERSION} $INSTALL_DIR
  sudo chown -R $USER:$USER $INSTALL_DIR
fi

# SSL setup
sudo mkdir -p $SSL_DIR
cd $SSL_DIR

echo "Generating SSL Certificates..."

# 1. Create CA
sudo openssl req -new -x509 -keyout ca.key -out ca.crt -days 3650 -subj "/CN=Kafka-CA/OU=IT/O=Training/L=Pune/ST=Maharashtra/C=IN" -passout pass:changeit

# 2. Generate keystore + keypair for each broker
for i in 1 2 3; do
  BROKER_KEY="broker$i.key"
  BROKER_CSR="broker$i.csr"
  BROKER_CERT="broker$i.crt"
  BROKER_P12="broker$i.p12"
  STORE_PASS="changeit"

  # Private key
  sudo openssl genrsa -out $BROKER_KEY 2048

  # CSR
  sudo openssl req -new -key $BROKER_KEY -out $BROKER_CSR -subj "/CN=broker$i"

  # Sign with CA
  sudo openssl x509 -req -in $BROKER_CSR -CA ca.crt -CAkey ca.key -CAcreateserial -out $BROKER_CERT -days 3650 -passin pass:changeit

  # Create PKCS12 keystore
  sudo openssl pkcs12 -export -in $BROKER_CERT -inkey $BROKER_KEY -out $BROKER_P12 -name broker$i -CAfile ca.crt -caname root -password pass:$STORE_PASS
done

sudo chown -R $USER:$USER $SSL_DIR

# Create data directories
for i in 1 2 3; do
  sudo mkdir -p ${DATA_DIR_BASE}${i}/logs
  sudo chown -R $USER:$USER ${DATA_DIR_BASE}${i}
done
sudo mkdir -p $LOG_DIR && sudo chown -R $USER:$USER $LOG_DIR

# Generate cluster ID
CLUSTER_ID=$($INSTALL_DIR/bin/kafka-storage.sh random-uuid)

# Broker configs
for i in 1 2 3; do
  PORT=$((9091 + i))
  CTRL_PORT=$((29090 + i))
  CONFIG_FILE="$INSTALL_DIR/config/kraft/server-$i.properties"

  cat <<EOF | sudo tee $CONFIG_FILE > /dev/null
process.roles=broker,controller
node.id=$i
controller.quorum.voters=1@localhost:29091,2@localhost:29092,3@localhost:29093
listeners=SSL://:909$i,CONTROLLER://:2909$i
advertised.listeners=SSL://localhost:909$i
listener.security.protocol.map=SSL:SSL,CONTROLLER:PLAINTEXT
inter.broker.listener.name=SSL
controller.listener.names=CONTROLLER
log.dirs=${DATA_DIR_BASE}${i}/logs
num.partitions=3
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=1
ssl.keystore.type=PKCS12
ssl.keystore.location=${SSL_DIR}/broker$i.p12
ssl.keystore.password=changeit
ssl.truststore.type=PEM
ssl.truststore.certificates=${SSL_DIR}/ca.crt
ssl.client.auth=none
group.initial.rebalance.delay.ms=0
EOF

  sudo -u $USER $INSTALL_DIR/bin/kafka-storage.sh format -t "$CLUSTER_ID" -c "$CONFIG_FILE"
done

# Systemd services
for i in 1 2 3; do
  SERVICE_FILE="/etc/systemd/system/kafka-$i.service"
  CONFIG_FILE="$INSTALL_DIR/config/kraft/server-$i.properties"
  sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Kafka Broker $i with SSL
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

sudo systemctl daemon-reload
for i in 1 2 3; do
  sudo systemctl enable kafka-$i
  sudo systemctl start kafka-$i
done

# Kafdrop setup
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
      KAFKA_PROPERTIES: "security.protocol=SSL,ssl.truststore.type=PEM,ssl.truststore.certificates=/certs/ca.crt"
    volumes:
      - ${SSL_DIR}:/certs
    restart: unless-stopped
EOF

sudo docker-compose -f /opt/docker-compose-kafdrop.yml up -d

echo "Kafka SSL cluster setup complete."
echo "Brokers: 9092, 9093, 9094 (SSL enabled)"
echo "Kafdrop: http://localhost:${KAFDROP_PORT}"
