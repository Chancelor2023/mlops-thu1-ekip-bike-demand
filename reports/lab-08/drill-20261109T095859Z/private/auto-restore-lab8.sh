#!/usr/bin/env bash
set -u

ROOT="${1:-}"
if [[ -z "$ROOT" || ! -f "$ROOT/private/restore-lab8.sh" ]]; then
  echo "STOP : script de récupération absent."
  exit 1
fi

sleep 180

for ATTEMPT in 1 2; do
  printf 'Récupération automatique, tentative %s\n' "$ATTEMPT"
  date -u +%Y-%m-%dT%H:%M:%SZ

  if bash "$ROOT/private/restore-lab8.sh" "$ROOT"; then
    echo "Commande de retour réussie ; vérification du service nécessaire."
    exit 0
  fi

  if [[ "$ATTEMPT" == 1 ]]; then
    sleep 5
  fi
done

echo "ÉCHEC : vérifier immédiatement le routage et les logs."
exit 1
