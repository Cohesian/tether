# Cohesian Tether — agent guidance

## Purpose

Maintain Tether, the common dependency-free bridge between K resource targets
and contributor-owned stores.

Tether owns protocol interpretation, URI projection, and explicit
consumer-directed materialization. It does not own K topology, contributor
content, credentials, or persistent consumer storage.

## Read first

| Need | Read |
|---|---|
| Tool overview | [`README.md`](README.md) |
| Contributor protocol | [`docs/CONTRIBUTOR-PROTOCOL.md`](docs/CONTRIBUTOR-PROTOCOL.md) |
| Contributor onboarding | [`docs/CONTRIBUTOR-ONBOARDING.md`](docs/CONTRIBUTOR-ONBOARDING.md) |
| Pull layouts | [`docs/MATERIALIZATION.md`](docs/MATERIALIZATION.md) |
| K resource overlay | [`../../k-graph/docs/RESOURCE-OVERLAY.md`](../../k-graph/docs/RESOURCE-OVERLAY.md) |
| Mathematical contract | [`../../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md`](../../../Organization/CONTRIBUTOR-STORE-RESOLUTION.md) |
| Research contributor | [`../research/contributor.toml`](../research/contributor.toml) |
| Studio contributor | [`../../studio/contributor.toml`](../../studio/contributor.toml) |

## Invariants

- $τ=(σ,(c,d,f))$ remains the complete resolution target.
- Domains and stores remain independent axes.
- `[[bindings]]` is the explicit domain–store–format relation.
- Relative package paths cannot escape the contributor workspace.
- Credentials never appear in protocols, inventories, or output.
- Resolution is informational and performs no content transfer.
- `pull` is the only transfer boundary and always names one store, destination,
  and layout explicitly.
- Contributor-specific layouts remain behind the common protocol.

## Validation

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m unittest discover -s tests
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m tether.cli contributor check ../research
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python -m tether.cli contributor check ../../studio
```
