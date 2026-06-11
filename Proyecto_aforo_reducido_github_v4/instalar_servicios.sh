#!/bin/bash
# instalar_servicios.sh
# Configura el SO y los servicios para el sistema de aforo.
# Ejecutar desde ~/proyecto_aforo/ despues de instalar_dependencias.sh

set -e

echo "=== [1/7] Instalando hostapd y dnsmasq ==="
sudo apt update
sudo apt install -y hostapd dnsmasq

echo "=== [2/7] Configurando IP fija para wlan0 ==="
# Verificar si ya existe el bloque para evitar duplicados
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    sudo bash -c 'cat >> /etc/dhcpcd.conf << EOF

interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF'
    echo "  IP fija wlan0 agregada."
else
    echo "  IP fija wlan0 ya existe, omitiendo."
fi

echo "=== [3/7] Configurando dnsmasq ==="
if [ -f /etc/dnsmasq.conf.bak ]; then
    echo "  dnsmasq ya fue configurado antes, omitiendo backup."
else
    sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
fi
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/aforo.local/192.168.4.1
EOF'

echo "=== [4/7] Configurando hostapd ==="
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

echo "=== [5/7] Apuntando hostapd a su configuracion ==="
sudo sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd || true

echo "=== [6/7] Deshabilitando hostapd y dnsmasq ==="
# Desmascarar primero por si systemd los enmascaro al instalar
sudo systemctl unmask hostapd.service || true
sudo systemctl unmask dnsmasq.service || true
sudo systemctl disable hostapd.service
sudo systemctl disable dnsmasq.service

echo "=== [7/7] Instalando y habilitando aforo-boot ==="
sudo bash -c 'cat > /etc/systemd/system/aforo-boot.service << EOF
[Unit]
Description=Aforo Boot Manager - Selector de modo
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/home/pi/proyecto_aforo/afov/bin/python /home/pi/proyecto_aforo/aforo/boot_manager.py
Restart=no

[Install]
WantedBy=multi-user.target
EOF'
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