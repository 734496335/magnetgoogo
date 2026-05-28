#!/bin/bash
curl -s -X POST http://127.0.0.1:3001/api/auth \
  -H 'Content-Type: application/json' \
  -d '{"password":"Maggoogo2026"}' \
  -i 2>&1 | head -20
