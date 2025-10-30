#!/bin/bash
set -e

# Kafka SSL Operations Script
# Adjust paths and parameters as per your setup.

KAFKA_HOME="/opt/kafka"
BOOTSTRAP_SERVER="localhost:9093"

# SSL certificate files
SSL_CA_CERT="/etc/kafka/ssl/ca.crt"
SSL_CLIENT_CERT="/etc/kafka/ssl/client.crt"
SSL_CLIENT_KEY="/etc/kafka/ssl/client.key"

CONFIG_FILE="/tmp/client-ssl.properties"

echo "[*] Generating temporary SSL config for Kafka client..."
cat > $CONFIG_FILE <<EOF
security.protocol=SSL
ssl.truststore.type=PEM
ssl.truststore.certificates=$SSL_CA_CERT
ssl.keystore.type=PEM
ssl.keystore.certificate.chain=$SSL_CLIENT_CERT
ssl.keystore.key=$SSL_CLIENT_KEY
EOF

echo "[1/4] Listing topics..."
$KAFKA_HOME/bin/kafka-topics.sh --list \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --command-config $CONFIG_FILE || echo "No topics found."

echo "[2/4] Creating topic 'test-topic'..."
$KAFKA_HOME/bin/kafka-topics.sh --create \
  --topic test-topic \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --replication-factor 1 \
  --partitions 3 \
  --command-config $CONFIG_FILE || echo "Topic may already exist."

echo "[3/4] Describing topic 'test-topic'..."
$KAFKA_HOME/bin/kafka-topics.sh --describe \
  --topic test-topic \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --command-config $CONFIG_FILE

echo "[4/4] Producing and consuming test messages..."
echo "hello from SSL Kafka client" | $KAFKA_HOME/bin/kafka-console-producer.sh \
  --topic test-topic \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --producer.config $CONFIG_FILE

$KAFKA_HOME/bin/kafka-console-consumer.sh \
  --topic test-topic \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --consumer.config $CONFIG_FILE \
  --from-beginning --timeout-ms 5000

echo "[✔] Kafka SSL connectivity and topic verification completed successfully."
