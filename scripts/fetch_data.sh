#!/usr/bin/env bash
set -euo pipefail

LOGIN="${1:?usage: fetch_data.sh <login> [out.json]}"
OUT="${2:-data/github.json}"
mkdir -p "$(dirname "$OUT")"

read -r -d '' QUERY <<'GQL' || true
query($login: String!) {
  user(login: $login) {
    login
    name
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { ...R } }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { ...R }
    }
  }
}
fragment R on Repository {
  name description url stargazerCount forkCount pushedAt isFork
  primaryLanguage { name color }
}
GQL

tmp="$(mktemp)"
gh api graphql -F login="$LOGIN" -f query="$QUERY" > "$tmp"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit("GraphQL error: "+json.dumps(d["errors"])) if d.get("errors") or not d.get("data",{}).get("user") else None' "$tmp"
mv "$tmp" "$OUT"
echo "wrote $OUT"
