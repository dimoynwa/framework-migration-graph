#!/usr/bin/env bash
# extract_yaml_keys.sh — extract Spring Boot YAML property keys
# Target project: /Users/dimo.drangov/DevelopmentTools
# No external dependencies. Requires bash 3.2+ (macOS default).

yaml_to_dotted_keys() {
    local file="$1"
    local -a stack_key=()
    local -a stack_indent=()
    local -a stack_has_child=()
    local in_list=0
    local list_indent=-1

    _make_path() {
        local key="$1"
        if (( ${#stack_key[@]} > 0 )); then
            local p; p=$(IFS=.; echo "${stack_key[*]}")
            echo "${p}.${key}"
        else
            echo "${key}"
        fi
    }

    _path_to_idx() {
        local idx="$1"
        local prefix="" j
        for (( j=0; j<=idx; j++ )); do
            [[ -z "$prefix" ]] && prefix="${stack_key[j]}" \
                               || prefix="${prefix}.${stack_key[j]}"
        done
        echo "$prefix"
    }

    _pop_to_indent() {
        local target="$1"
        local new_len=0 i
        for (( i=0; i<${#stack_indent[@]}; i++ )); do
            (( stack_indent[i] < target )) && (( new_len++ ))
        done
        for (( i=new_len; i<${#stack_key[@]}; i++ )); do
            if [[ "${stack_has_child[i]}" == "0" ]]; then
                _path_to_idx "$i"
            fi
        done
        stack_key=("${stack_key[@]:0:$new_len}")
        stack_indent=("${stack_indent[@]:0:$new_len}")
        stack_has_child=("${stack_has_child[@]:0:$new_len}")
    }

    _mark_top_has_child() {
        (( ${#stack_has_child[@]} > 0 )) || return
        local top=$(( ${#stack_has_child[@]} - 1 ))
        stack_has_child[$top]=1
    }

    _emit_list_parent_if_needed() {
        (( ${#stack_has_child[@]} > 0 )) || return
        local top=$(( ${#stack_has_child[@]} - 1 ))
        if [[ "${stack_has_child[$top]}" == "0" ]]; then
            _path_to_idx "$top"
            stack_has_child[$top]=1
        fi
    }

    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" =~ ^[[:space:]]*$  ]] && continue
        [[ "$line" =~ ^[[:space:]]*#  ]] && continue

        if [[ "$line" == "---" || "$line" =~ ^---[[:space:]] ]]; then
            _pop_to_indent 0
            stack_key=(); stack_indent=(); stack_has_child=()
            in_list=0; list_indent=-1
            continue
        fi

        local content="${line#"${line%%[! ]*}"}"
        local indent=$(( ${#line} - ${#content} ))

        if [[ "$content" =~ ^-[[:space:]] ]] || [[ "$content" == "-" ]]; then
            _emit_list_parent_if_needed
            in_list=1
            list_indent=$indent
            continue
        fi

        if (( in_list && indent <= list_indent )); then
            in_list=0; list_indent=-1
        fi
        (( in_list && indent > list_indent )) && continue

        _pop_to_indent "$indent"

        local nocomment
        nocomment=$(echo "$content" | sed "s/ #[^'\"]*$//")
        local key="${nocomment%%:*}"
        local rest="${nocomment#*:}"
        rest="${rest#"${rest%%[! ]*}"}"

        [[ "$key" =~ ^[A-Za-z0-9_@.-] ]] || continue
        [[ "$key" =~ [[:space:]] ]]        && continue

        local path; path=$(_make_path "$key")

        if [[ -z "$rest" || "$rest" == "~" || "$rest" =~ ^# \
              || "$rest" == "|" || "$rest" == ">" \
              || "$rest" == "|-" || "$rest" == ">-" ]]; then
            _mark_top_has_child
            stack_key+=("$key")
            stack_indent+=("$indent")
            if [[ "$rest" == "~" ]]; then
                stack_has_child+=(1)
                echo "$path"
            else
                stack_has_child+=(0)
            fi
        else
            _mark_top_has_child
            echo "$path"
        fi

    done < "$file"

    _pop_to_indent 0
}

PROJECT_ROOT="/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-switch"

if [[ ! -d "$PROJECT_ROOT/src/main/resources" ]]; then
    echo "Warning: $PROJECT_ROOT/src/main/resources not found — no YAML files scanned." >&2
    exit 0
fi

find "$PROJECT_ROOT/src/main/resources" \
    \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null \
| while IFS= read -r f; do
    yaml_to_dotted_keys "$f"
done | sort -u