# No allowed outbound edges for argus-ci (tooling) beyond wildcard targe

## Night conductor remediation



### Finding
```json
{
  "id": "ARGUS-CI-INV-001",
  "rule": "call_graph_rules.allowed_calls",
  "severity": "MEDIUM",
  "type": "config_gap",
  "title": "No allowed outbound edges for argus-ci (tooling) beyond wildcard targets",
  "description": "argus-ci has role 'tooling'. Its only permitted edges are the wildcard edges to agent-composer and argus-cortex. CI pipelines usually run smoke or integration tests against suite services. Any env var such as DARKROOM, CURATOR, LENS, COMFYUI or VOLUPTAS in argus-ci would be treated as a forbidden call (argus-ci -> argus-darkroom, argus-curator, argus-lens or voluptas). Rule ARGUS-CI-INV-004 also forbids the rag_and_chat domain in argus-ci, which conflicts with the wildcard permitting calls to agent-composer.",
  "evidence": "call_graph_rules.allowed_calls has no 'from: argus-ci' entry; service_url_env_vars maps DARKROOM, CURATOR, LENS, COMFYUI and VOLUPTAS to services.",
  "location": "architecture_rules: call_graph_rules",
  "confidence": "medium",
  "verified_in_code": false,
  "recommendation": "Grep argus-ci workflows, compose files and test configs for the listed env fragments. If CI calls these services by design, add explicit tooling allowances (e.g. 'from: argus-ci, to: *, note: CI smoke tests') or exempt the tooling role from call-graph checks."
}
```

### Agent work pack
- URL: http://192.168.1.198:8765/audit/packs/pack-ARGUS-CI-INV-001
- id: `pack-ARGUS-CI-INV-001`
- Discover: `GET /audit/packs?q=<repo-or-title>`

Draft PR — do not auto-merge.

