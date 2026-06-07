#!/bin/bash
# instalar_servicios.sh
# Configura el SO y los servicios para el sistema de aforo.
# Ejecutar desde ~/proyecto_aforo/ despues de instalar_dependencias.sh

set -e

echo "=== [1/8] Instalando hostapd y dnsmasq ==="
sudo apt update
sudo apt install -y hostapd dnsmasq

echo "=== [2/8] Configurando IP fija para wlan0 ==="
sudo bash -c 'cat >> /etc/dhcpcd.conf << EOF

interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF'

echo "=== [3/8] Configurando dnsmasq ==="
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/aforo.local/192.168.4.1
EOF'

echo "=== [4/8] Configurando hostapd ==="
sudo bash -c 'cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan0
driver=nl80211
ssid=aforo-config
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=12345678
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF'

echo "=== [5/8] Apuntando hostapd a su configuracion ==="
sudo sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd || true

echo "=== [6/8] Deshabilitando hostapd y dnsmasq ==="
sudo systemctl disable hostapd.service
sudo systemctl disable dnsmasq.service

echo "=== [7/8] Ignorando wlan0 en NetworkManager ==="
sudo bash -c 'cat >> /etc/NetworkManager/NetworkManager.conf << EOF

[keyfile]
unmanaged-devices=interface-name:wlan0
EOF'

echo "=== [8/8] Instalando y habilitando aforo-boot ==="
sudo cp /home/pi/proyecto_aforo/services/aforo-boot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aforo-boot.service

# Verificacion final
echo ""
echo "--- Verificacion de servicios ---"
echo -n "hostapd:    "; systemctl is-enabled hostapd
echo -n "dnsmasq:    "; systemctl is-enabled dnsmasq
echo -n "aforo-boot: "; systemctl is-enabled aforo-boot

echo ""
echo "=== Listo. Ejecutar sudo reboot para aplicar cambios ==="