#!/usr/bin/env bash
set -euo pipefail

case "${RENEWED_LINEAGE:-}" in
  /etc/letsencrypt/live/mcf-aws|/etc/letsencrypt/live/mcf-azure) ;;
  *) exit 0 ;;
esac

/usr/local/bin/k3s kubectl -n issues create secret tls issues-app-tls \
  --cert="${RENEWED_LINEAGE}/fullchain.pem" \
  --key="${RENEWED_LINEAGE}/privkey.pem" \
  --dry-run=client -o yaml \
  | /usr/local/bin/k3s kubectl -n issues apply -f -