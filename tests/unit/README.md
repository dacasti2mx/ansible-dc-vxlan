# Unit tests

Deterministic unit tests for the `dtc` plugins, following the
[`ansible-test units`](https://docs.ansible.com/ansible/latest/dev_guide/testing_units.html)
convention. They run with mocks only — **no live NDFC / Nexus Dashboard** —
so they reproduce plugin-level behavior that the integration tests cannot
(see issue #818).

## Layout

```
tests/unit/
├── requirements.txt                              # extra test deps (currently none)
└── plugins/
    ├── plugin_utils/test_pipeline_base.py        # config-save policy + preprovision gate (#813)
    └── action/dtc/test_fabric_deploy_manager.py  # config-save response contract (#813)
```

## Running with ansible-test (what CI runs)

From the **installed collection** path
(`.../ansible_collections/cisco/nac_dc_vxlan`):

```bash
# In a container (matches CI):
ansible-test units --docker -v

# Or against the local interpreter:
ansible-test units --python 3.12 -v
```

## Running with pytest (quick local loop)

From a checkout, point `PYTHONPATH` at the collections root so the
`ansible_collections.cisco.nac_dc_vxlan...` imports resolve:

```bash
PYTHONPATH=<collections_root> python -m pytest tests/unit/ -v --import-mode=importlib
```

where `<collections_root>` is the directory that contains
`ansible_collections/` (e.g. `collections/` in the homelab repo).

## What is covered

`pipeline_base._config_save` + `_fabric_has_preprovisioned_switches`:

| config-save result            | data model      | expected   |
|-------------------------------|-----------------|------------|
| HTTP 200                      | any             | ok         |
| HTTP 500                      | pre-provisioned | non-fatal  |
| HTTP 500                      | not preprov     | **fatal**  |
| HTTP 400                      | any             | fatal      |
| missing / malformed `msg`     | any             | fatal      |

`fabric_deploy_manager` (operation `config_save`): a non-200 response sets
`failed=True` with the raw NDFC response **intact** (so `RETURN_CODE` survives
for `pipeline_base` to inspect); 200 does not fail.
