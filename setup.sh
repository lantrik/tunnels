#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Run as root"; exit 1; fi

read -rp "Домен (example.com): " DOMAIN
DOMAIN="${DOMAIN%%/}"
read -rp "SSH порт для Sish [2222]: " SSH_PORT
SSH_PORT="${SSH_PORT:-2222}"
read -rp "Email для Let's Encrypt: " LE_EMAIL
read -rp "Токен админ-панели (любой сложный строковый): " ADMIN_TOKEN

echo "Вставьте публичный SSH-ключ (.pub) одной строкой и нажмите Enter:"
read -r PUBKEY_LINE
if [[ -z "$PUBKEY_LINE" || "$PUBKEY_LINE" != ssh-* ]]; then
  echo "Неверный ключ"; exit 1
fi

apt update
apt install -y docker.io docker-compose
systemctl enable --now docker

mkdir -p /srv/sish-public-keys
echo "$PUBKEY_LINE" > /srv/sish-public-keys/user.pub
chmod 644 /srv/sish-public-keys/user.pub

mkdir -p /root/sish
cat > /root/sish/docker-compose.yml <<'YAML'
services:
  sish:
    image: antoniomika/sish:latest
    container_name: sish
    restart: always
    command: >
      --ssh-address=:__SSH_PORT__
      --http-address=:80
      --https-address=:443
      --domain=__DOMAIN__
      --bind-random-subdomains=false
      --authentication=true
      --authentication-keys-directory=/pubkeys
      --admin-console
      --admin-console-token=__ADMIN_TOKEN__
      --load-templates
      --https
      --https-ondemand-certificate
      --https-ondemand-certificate-accept-terms
      --https-ondemand-certificate-email=__LE_EMAIL__
      --verify-dns=false
      --idle-connection=false
      --ping-client
      --ping-client-interval=30s
      --ping-client-timeout=120s
    ports:
      - "80:80"
      - "443:443"
      - "__SSH_PORT__:__SSH_PORT__"
    volumes:
      - /srv/sish-public-keys:/pubkeys:ro
YAML

sed -i \
  -e "s/__DOMAIN__/${DOMAIN//\//\\/}/g" \
  -e "s/__SSH_PORT__/${SSH_PORT}/g" \
  -e "s/__ADMIN_TOKEN__/${ADMIN_TOKEN//\//\\/}/g" \
  -e "s/__LE_EMAIL__/${LE_EMAIL//\//\\/}/g" \
  /root/sish/docker-compose.yml

cd /root/sish
docker-compose up -d

echo
echo "✓ Sish запущен"
echo "DNS: A ${DOMAIN} -> ваш IP, A *.${DOMAIN} -> ваш IP"
echo "Проверьте:   dig ${DOMAIN}  |  dig sub.${DOMAIN}"
echo
echo "Админ-консоль: https://${DOMAIN}/_sish/console?x-authorization=${ADMIN_TOKEN}"
echo
echo "Пример подключения клиента:"
echo "ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes -N -R web1:80:localhost:8000 root@${DOMAIN}"
echo
