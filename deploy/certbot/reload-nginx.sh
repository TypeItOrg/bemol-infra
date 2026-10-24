#!/bin/sh
set -eu

# Certificate renewal must not start an inactive Nginx service.
if systemctl is-active --quiet nginx; then
    nginx -t
    systemctl reload nginx
fi
