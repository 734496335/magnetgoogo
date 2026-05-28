#!/bin/bash
sudo sed -i 's/DASH_PASS=MagGoogo2026/DASH_PASS=Maggoogo2026/' /etc/systemd/system/analytics-server.service
sudo systemctl daemon-reload
sudo systemctl restart analytics-server
# Test
sleep 1
curl -s -X POST http://127.0.0.1:3001/api/auth \
  -H 'Content-Type: application/json' \
  -d '{"password":"Maggoogo2026"}' \
  -i 2>&1 | head -10
