#!/usr/bin/env bash
# Regenerates all .claude/references/ MD files by scanning the current app code.
# Run manually: bash .claude/update_skill.sh
# Triggered by: user says "update md files" at end of a chat session.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)/erp_ai_integration"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)/references"
HOOKS="$APP_DIR/hooks.py"

mkdir -p "$OUT_DIR"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# ═══════════════════════════════════════════════════════════════════════════════
# 1. app_map.md — full file + method inventory
# ═══════════════════════════════════════════════════════════════════════════════
{
echo "# app_map — erp_ai_integration"
echo ""
echo "_Generated: ${TIMESTAMP}_"
echo ""

echo "## Modules"
echo ""
find "$APP_DIR" -maxdepth 1 -mindepth 1 -type d \
  | grep -v '__pycache__\|\.git\|\.claude' \
  | xargs -I{} basename {} \
  | sort \
  | while read -r m; do echo "- $m"; done
echo ""

echo "## Python files"
echo ""
PY_FILES=$(find "$APP_DIR" -name "*.py" | grep -v '__pycache__' | sort)
PY_COUNT=$(echo "$PY_FILES" | wc -l | tr -d ' ')
echo "_Total: ${PY_COUNT}_"
echo ""
echo "$PY_FILES" | while read -r f; do
  echo "- ${f#$APP_DIR/}"
done
echo ""

echo "## JavaScript files"
echo ""
JS_FILES=$(find "$APP_DIR" -name "*.js" | grep -v '__pycache__' | sort)
JS_COUNT=$(echo "$JS_FILES" | wc -l | tr -d ' ')
echo "_Total: ${JS_COUNT}_"
echo ""
echo "$JS_FILES" | while read -r f; do
  echo "- ${f#$APP_DIR/}"
done
echo ""

echo "## JSON files"
echo ""
JSON_FILES=$(find "$APP_DIR" -name "*.json" | grep -v '__pycache__' | sort)
JSON_COUNT=$(echo "$JSON_FILES" | wc -l | tr -d ' ')
echo "_Total: ${JSON_COUNT}_"
echo ""
echo "$JSON_FILES" | while read -r f; do
  echo "- ${f#$APP_DIR/}"
done
echo ""

echo "## Doctypes"
echo ""
find "$APP_DIR" -path "*/doctype/*" -name "*.json" \
  | grep -v '__pycache__' \
  | sort \
  | while read -r jf; do
    dt_dir="$(dirname "$jf")"
    dt_name="$(basename "$jf" .json)"
    py_file="$dt_dir/$dt_name.py"
    js_file="$dt_dir/$dt_name.js"
    echo "### $dt_name"
    echo "- Path: \`${dt_dir#$APP_DIR/}\`"
    [[ -f "$py_file" ]] && echo "- Controller: \`${py_file#$APP_DIR/}\`" || echo "- Controller: none"
    [[ -f "$js_file" ]] && echo "- Client script: \`${js_file#$APP_DIR/}\`" || echo "- Client script: none"
    if [[ -f "$py_file" ]]; then
      methods=$(grep -n "^\s*def \|^def " "$py_file" 2>/dev/null \
        | sed 's/.*def //;s/(.*/:/' | sed 's/^/  - /' || true)
      [[ -n "$methods" ]] && echo "- Methods:" && echo "$methods"
    fi
    echo ""
  done

echo "## Module-level controllers"
echo ""
find "$APP_DIR" -maxdepth 2 -name "*.py" \
  | grep -v '__pycache__\|__init__\|/doctype/' \
  | sort \
  | while read -r f; do
    rel="${f#$APP_DIR/}"
    pub=$(grep -n "^def " "$f" 2>/dev/null | sed 's/def //;s/(.*/:/' | sed 's/^/  - /' || true)
    echo "### $rel"
    [[ -n "$pub" ]] && echo "Functions:" && echo "$pub"
    echo ""
  done

echo "## Whitelisted API methods"
echo ""
grep -rn "@frappe.whitelist" "$APP_DIR" --include="*.py" \
  | grep -v '__pycache__' \
  | while IFS=: read -r file line rest; do
    fn_line=$(sed -n "$((line+1))p" "$file" | sed 's/.*def //;s/(.*//')
    echo "- \`${file#$APP_DIR/}:$((line+1))\` — \`$fn_line\`"
  done
echo ""

echo "## hooks.py — doc_events"
echo ""
awk '/^doc_events\s*=/{found=1} found{print; if(/^}$/) exit}' "$HOOKS"
echo ""

echo "## hooks.py — overrides"
echo ""
grep -A5 "^override_doctype_class" "$HOOKS" | grep -v "^#" || true
echo ""
grep -A5 "^override_doctype_dashboards" "$HOOKS" | grep -v "^#" || true
echo ""

echo "## hooks.py — fixtures & lifecycle"
echo ""
grep "^fixtures" "$HOOKS" || true
grep -E "^(after_install|after_migrate|before_install|before_uninstall)" "$HOOKS" || true
echo ""

} > "$OUT_DIR/app_map.md"
echo "[update_skill] app_map.md done"

# ═══════════════════════════════════════════════════════════════════════════════
# 2. doctypes.md — per-doctype detail
# ═══════════════════════════════════════════════════════════════════════════════
{
echo "# doctypes — erp_ai_integration"
echo ""
echo "_Generated: ${TIMESTAMP}_"
echo ""

DT_COUNT=0
find "$APP_DIR" -path "*/doctype/*" -name "*.json" \
  | grep -v '__pycache__' \
  | sort \
  | while read -r jf; do
    dt_dir="$(dirname "$jf")"
    dt_name="$(basename "$jf" .json)"
    module=$(echo "${dt_dir#$APP_DIR/}" | cut -d/ -f1)
    py_file="$dt_dir/$dt_name.py"
    js_file="$dt_dir/$dt_name.js"

    echo "## $dt_name"
    echo ""
    echo "| Key | Value |"
    echo "|-----|-------|"
    echo "| Module | $module |"
    echo "| Path | \`${dt_dir#$APP_DIR/}\` |"
    if [[ -f "$py_file" ]]; then
      echo "| Controller | \`${py_file#$APP_DIR/}\` |"
    else
      echo "| Controller | none |"
    fi
    if [[ -f "$js_file" ]]; then
      echo "| Client script | \`${js_file#$APP_DIR/}\` |"
    else
      echo "| Client script | none |"
    fi

    # doc_events registered for this doctype (match display name from JSON)
    dt_label=$(python3 -c "
import json, sys
try:
    d = json.load(open('$jf'))
    print(d.get('name',''))
except: pass
" 2>/dev/null || true)
    if [[ -n "$dt_label" ]]; then
      events=$(awk -v dt="\"$dt_label\"" '
        $0 ~ dt && /":/ { found=1 }
        found { print; if (/^\t},$/ || /^\t},?$/) { found=0 } }
      ' "$HOOKS" | grep -v "^#" | head -20 || true)
      if [[ -n "$events" ]]; then
        echo "| doc_events | see hooks.md |"
      fi
    fi
    echo ""

    if [[ -f "$py_file" ]]; then
      pub=$(grep -n "^def \|^\s*def " "$py_file" 2>/dev/null \
        | sed 's/.*def //;s/(.*/:/' || true)
      wl_lines=$(grep -n "@frappe.whitelist" "$py_file" 2>/dev/null \
        | cut -d: -f1 || true)
      if [[ -n "$pub" ]]; then
        echo "### Methods"
        echo ""
        echo "| Method | Whitelisted |"
        echo "|--------|-------------|"
        while IFS= read -r line; do
          lineno=$(echo "$line" | cut -d: -f1)
          name=$(echo "$line" | sed 's/^[0-9]*://')
          is_wl="no"
          prev=$((lineno - 1))
          if echo "$wl_lines" | grep -q "^$prev$"; then
            is_wl="yes"
          fi
          echo "| \`$name\` | $is_wl |"
        done <<< "$(grep -n "^def \|^\s*def " "$py_file" 2>/dev/null | sed 's/.*def //;s/(.*//' | nl -ba | awk '{print NR": "$2}'  || true)"
        echo ""
      fi
    fi

    echo "---"
    echo ""
  done

} > "$OUT_DIR/doctypes.md"
echo "[update_skill] doctypes.md done"

# ═══════════════════════════════════════════════════════════════════════════════
# 3. hooks.md — full hooks.py summary
# ═══════════════════════════════════════════════════════════════════════════════
{
echo "# hooks — erp_ai_integration"
echo ""
echo "_Generated: ${TIMESTAMP}_"
echo ""

echo "## doc_events"
echo ""
echo "\`\`\`python"
awk '/^doc_events\s*=/{found=1} found{print; if(/^}$/) exit}' "$HOOKS"
echo "\`\`\`"
echo ""

echo "## override_doctype_class"
echo ""
echo "\`\`\`python"
awk '/^override_doctype_class\s*=/{found=1} found{print; if(/^}/) exit}' "$HOOKS"
echo "\`\`\`"
echo ""

echo "## override_doctype_dashboards"
echo ""
echo "\`\`\`python"
awk '/^override_doctype_dashboards\s*=/{found=1} found{print; if(/^}/) exit}' "$HOOKS"
echo "\`\`\`"
echo ""

echo "## doctype_js (client scripts injected into standard doctypes)"
echo ""
echo "\`\`\`python"
grep "^app_include_js\|^doctype_js" "$HOOKS" | grep -v "^#" || true
awk '/^doctype_js\s*=/{found=1} found{print; if(/^}/) exit}' "$HOOKS"
echo "\`\`\`"
echo ""

echo "## fixtures"
echo ""
echo "\`\`\`python"
grep "^fixtures" "$HOOKS" || true
echo "\`\`\`"
echo ""

echo "## App lifecycle"
echo ""
echo "\`\`\`python"
grep -E "^(after_install|after_migrate|before_install|before_uninstall|after_install)" "$HOOKS" || true
echo "\`\`\`"
echo ""

echo "## scheduler_events"
echo ""
sched=$(grep -A3 "^scheduler_events" "$HOOKS" 2>/dev/null | grep -v "^#" || true)
if [[ -z "$sched" ]]; then
  echo "_None registered (all commented out)._"
else
  echo "\`\`\`python"
  echo "$sched"
  echo "\`\`\`"
fi
echo ""

} > "$OUT_DIR/hooks.md"
echo "[update_skill] hooks.md done"

# ═══════════════════════════════════════════════════════════════════════════════
# 4. api.md — all @frappe.whitelist() methods
# ═══════════════════════════════════════════════════════════════════════════════
{
echo "# api — erp_ai_integration"
echo ""
echo "_Generated: ${TIMESTAMP}_"
echo ""
echo "All \`@frappe.whitelist()\` methods. Call from JS:"
echo "\`frappe.call({ method: 'erp_ai_integration.<dotted.path>', args: {...} })\`"
echo ""

current_file=""
grep -rn "@frappe.whitelist" "$APP_DIR" --include="*.py" \
  | grep -v '__pycache__' \
  | sort \
  | while IFS=: read -r file line rest; do
    rel="${file#$APP_DIR/}"
    fn_line=$(sed -n "$((line+1))p" "$file" | sed 's/.*def //;s/(.*//')
    # print file header when file changes
    if [[ "$file" != "$current_file" ]]; then
      echo "## $rel"
      echo ""
      echo "| Method | Line |"
      echo "|--------|------|"
      current_file="$file"
    fi
    echo "| \`$fn_line\` | $((line+1)) |"
  done
echo ""

echo "## Total"
echo ""
TOTAL=$(grep -rn "@frappe.whitelist" "$APP_DIR" --include="*.py" | grep -v '__pycache__' | wc -l | tr -d ' ')
echo "_${TOTAL} whitelisted methods_"

} > "$OUT_DIR/api.md"
echo "[update_skill] api.md done"

# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "[update_skill] All MD files updated at ${TIMESTAMP}"
echo "  app_map.md   — modules, files, methods, hooks summary"
echo "  doctypes.md  — per-doctype controller + client script detail"
echo "  hooks.md     — full hooks.py (doc_events, overrides, fixtures)"
echo "  api.md       — all @frappe.whitelist() methods"
