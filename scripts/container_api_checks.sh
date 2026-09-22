#!/usr/bin/env bash
# HTTP-level checks against a running F1Grid API (deployed mode). Works against a
# Docker container or a bare uvicorn - it only speaks HTTP. Docker-specific checks
# (non-root uid, stop/start) live in the CI workflow.
#
# Usage: container_api_checks.sh BASE_URL ALLOWED_ORIGIN DISALLOWED_ORIGIN
# Every assertion failure exits non-zero. No assertion is ever skipped.
set -euo pipefail

BASE="${1:?BASE_URL required}"
ALLOWED_ORIGIN="${2:?ALLOWED_ORIGIN required}"
DISALLOWED_ORIGIN="${3:?DISALLOWED_ORIGIN required}"

PY="${PYTHON:-python3}"
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "== /about: real data, saved models, model card =="
curl -fsS "$BASE/about" | "$PY" -c '
import sys, json
d = json.load(sys.stdin)
assert d.get("is_real_data") is True, "is_real_data != true: %r" % d.get("is_real_data")
assert d.get("used_saved_models") is True, "used_saved_models != true: %r" % d.get("used_saved_models")
card = d.get("model_card") or ""
assert len(card) > 50, "model_card too short/empty: %d" % len(card)
print("  is_real_data=True used_saved_models=True model_card=%d chars backend=%s"
      % (len(card), d.get("race_model_backend")))
' || fail "/about assertions"
pass "/about"

echo "== pick a real race from /races =="
read -r SEASON ROUND EVENT <<EOF
$(curl -fsS "$BASE/races" | "$PY" -c '
import sys, json
races = json.load(sys.stdin)
assert races, "no races returned"
r = races[-1]
print(r["season"], r["round"], r["event"])
')
EOF
echo "  using $SEASON R$ROUND $EVENT"

echo "== GET prediction: strategy complexity field present =="
curl -fsS "$BASE/predictions/$SEASON/$ROUND" | "$PY" -c '
import sys, json
d = json.load(sys.stdin)
assert d.get("is_real_data") is True, "prediction is_real_data != true"
assert d.get("predictions"), "no driver predictions"
m = d.get("strategy_meter")
assert m, "strategy_meter missing"
label = m.get("label") or ""
assert "Strategy complexity" in label, "unexpected meter label: %r" % label
print("  strategy_meter.label=%r state=%s is_confidence=%s"
      % (label, m.get("state"), m.get("is_confidence")))
' || fail "strategy complexity field"
pass "strategy complexity field on prediction"

echo "== publish refused (403) in deployed mode =="
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/predictions/$SEASON/$ROUND/publish")"
[ "$code" = "403" ] || fail "publish expected 403, got $code"
pass "publish -> 403"

echo "== score refused (403) in deployed mode =="
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/predictions/$SEASON/$ROUND/score")"
[ "$code" = "403" ] || fail "score expected 403, got $code"
pass "score -> 403"

echo "== CORS: allowed origin preflight gets ACAO header =="
hdr="$(curl -s -D - -o /dev/null -X OPTIONS \
  -H "Origin: $ALLOWED_ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  "$BASE/about" | tr -d '\r')"
acao="$(echo "$hdr" | grep -i '^access-control-allow-origin:' | awk '{print $2}' || true)"
[ "$acao" = "$ALLOWED_ORIGIN" ] || fail "allowed origin: expected ACAO=$ALLOWED_ORIGIN, got '${acao:-<none>}'"
pass "CORS allowed origin -> ACAO=$acao"

echo "== CORS: disallowed origin preflight gets NO ACAO header =="
hdr="$(curl -s -D - -o /dev/null -X OPTIONS \
  -H "Origin: $DISALLOWED_ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  "$BASE/about" | tr -d '\r')"
if echo "$hdr" | grep -iq "^access-control-allow-origin: *$DISALLOWED_ORIGIN"; then
  fail "disallowed origin was granted an ACAO header"
fi
pass "CORS disallowed origin -> no ACAO"

echo "ALL HTTP CHECKS PASSED"
