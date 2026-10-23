#!/usr/bin/env bash
# Prepare a fresh Ubuntu 22.04 or 24.04 VPS. Run once, as root:
#   sudo bash deploy/bootstrap_server.sh
# Installs Docker, a non-root deploy user, a firewall, fail2ban, and
# unattended security upgrades. It does not clone the repository.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/bootstrap_server.sh" >&2
  exit 1
fi

if [ ! -r /etc/os-release ]; then
  echo "This script supports Ubuntu 22.04 and 24.04." >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}:${VERSION_ID:-}" in
  ubuntu:22.04|ubuntu:24.04) ;;
  *)
    echo "This script supports Ubuntu 22.04 and 24.04 (found ${PRETTY_NAME:-unknown})." >&2
    exit 1
    ;;
esac

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  git \
  ufw \
  fail2ban \
  unattended-upgrades \
  apt-listchanges

bash "$(cd "$(dirname "$0")/.." && pwd)/scripts/ci/install_backup_tools.sh"

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

if ! id deploy >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash deploy
fi
usermod -aG docker deploy
install -d -o deploy -g deploy -m 0750 /opt/anyq
install -d -o deploy -g deploy -m 0750 /var/backups/anyq
install -d -o deploy -g deploy -m 0700 /home/deploy/.ssh
if [ ! -f /home/deploy/.ssh/authorized_keys ]; then
  touch /home/deploy/.ssh/authorized_keys
  chown deploy:deploy /home/deploy/.ssh/authorized_keys
  chmod 600 /home/deploy/.ssh/authorized_keys
fi

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat > /etc/fail2ban/jail.d/anyq-sshd.local <<'EOF'
[sshd]
enabled = true
port = 22
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades

echo
echo "Bootstrap finished."
echo "Next steps:"
echo "  1. Add an SSH public key to /home/deploy/.ssh/authorized_keys"
echo "  2. Confirm: ssh deploy@<server> true"
echo "  3. Clone the repository into /opt/anyq as the deploy user"
echo "  4. Follow docs/DEPLOY.md from the environment file onward"
echo
echo "Password login for SSH is unchanged. Disable it only after the deploy key works."
echo "The deploy user is in the docker group and can run the production stack."
echo "age and rclone are installed. Backup settings belong in deploy/.env, not in git."
