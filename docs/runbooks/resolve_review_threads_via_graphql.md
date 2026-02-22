# Runbook: Resolve review threads via GraphQL (required_conversation_resolution)

## Purpose

- Use when a PR is mergeable and CI-green but merge is blocked by `required_conversation_resolution` due to unresolved review threads (often bot reviews).
- This is deterministic and avoids UI actions or admin bypass.

## Preconditions

- `gh auth status` is OK
- You have permission to resolve review threads on the repo

## Step 1 — Find unresolved, non-outdated threads

Replace `PR_NUMBER` and repo owner/name as needed.

```bash
gh api graphql --input - --jq '
  .data.repository.pullRequest.reviewThreads.nodes
  | map(select(.isResolved==false and .isOutdated==false))
  | {unresolved: length,
     details: (map({id, path, line,
                    author: .comments.nodes[0].author.login,
                    snippet: (.comments.nodes[0].bodyText | tostring)}))}
' <<'JSON'
{
  "query": "query{repository(owner:\"jannekbuengener\",name:\"Claire_de_Binare\"){pullRequest(number:PR_NUMBER){reviewThreads(first:100){nodes{id isResolved isOutdated path line comments(first:1){nodes{author{login} bodyText}}}}}}}"
}
JSON
```

## Step 2 — Resolve a specific thread

Replace `THREAD_ID_HERE` with the returned `id`.

```bash
gh api graphql --input - --jq '.data.resolveReviewThread.thread.isResolved' <<'JSON'
{
  "query": "mutation{resolveReviewThread(input:{threadId:\"THREAD_ID_HERE\"}){thread{isResolved}}}"
}
JSON
```

## Step 3 — Re-check unresolved count (must be 0)

```bash
gh api graphql --input - --jq '
  .data.repository.pullRequest.reviewThreads.nodes
  | {total:length, unresolved:(map(select(.isResolved==false and .isOutdated==false))|length)}
' <<'JSON'
{
  "query": "query{repository(owner:\"jannekbuengener\",name:\"Claire_de_Binare\"){pullRequest(number:PR_NUMBER){reviewThreads(first:100){nodes{isResolved isOutdated}}}}}"
}
JSON
```

## Step 4 — Merge normally (no admin bypass)

```bash
gh pr checks PR_NUMBER
gh pr merge PR_NUMBER --merge --delete-branch
```

## Notes

- Prefer resolving only bot threads that contain no actionable requests.
- If the GraphQL mutation fails due to permissions, escalate to repo admin/maintainer policy decision.
