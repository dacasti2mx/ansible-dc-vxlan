# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# MIT License (see the collection source for the full text).
#
# Unit tests for the config-save error policy in pipeline_base.
# Covers issue #813 / PR #819: an HTTP 500 from config-save is non-fatal ONLY
# when the data model declares pre-provisioned switches; every other case stays
# fatal. Uses only the Python stdlib (unittest.mock) — no live NDFC.
from __future__ import absolute_import, division, print_function

__metaclass__ = type

from unittest import mock

import pytest

from ansible_collections.cisco.nac_dc_vxlan.plugins.plugin_utils import pipeline_base
from ansible_collections.cisco.nac_dc_vxlan.plugins.plugin_utils.pipeline_base import (
    PipelineRunnerBase,
)


# --- sample data models ----------------------------------------------------

PREPROV_DM = {
    "vxlan": {"topology": {"switches": [
        {"name": "spine1", "poap": {"preprovision": {"serial_number": "ABC123"}}},
        {"name": "leaf1"},
    ]}}
}

NON_PREPROV_DM = {
    "vxlan": {"topology": {"switches": [
        {"name": "leaf1", "poap": {"bootstrap": True}},
        {"name": "leaf2"},
    ]}}
}


# --- minimal concrete runner ----------------------------------------------

class _DummyRunner(PipelineRunnerBase):
    """
    Concrete runner that skips the heavy base __init__ (registry load) and sets
    only the attributes _config_save / the helper actually read. This lets us
    unit-test the config-save policy in isolation.
    """

    REGISTRY_KEY = "create_resources"
    OPERATION = "create"

    def __init__(self, executor, data_model):
        # Intentionally do NOT call super().__init__ (avoids RegistryLoader).
        self.executor = executor
        self.data_model = data_model
        self.fabric_name = "PREPROV1"
        self.fabric_type = "VXLAN_EVPN"

    def _resolve_step_data(self, resource_name, step):  # abstract -> no-op
        return ([], "merged")


def _runner(execute_plugin_result, data_model):
    """Build a runner whose executor returns the given config-save result."""
    executor = mock.Mock()
    executor.execute_plugin.return_value = execute_plugin_result
    return _DummyRunner(executor=executor, data_model=data_model)


# --- _fabric_has_preprovisioned_switches ----------------------------------

@pytest.mark.parametrize("data_model, expected", [
    (PREPROV_DM, True),                                                   # preprovision set
    (NON_PREPROV_DM, False),                                              # bootstrap only
    ({"vxlan": {"topology": {"switches": [{"name": "x"}]}}}, False),      # no poap
    ({}, False),                                                         # empty / missing keys
    ({"vxlan": {"topology": {"switches": [
        {"name": "x", "poap": {"preprovision": {}}}]}}}, False),         # empty preprovision -> falsy
])
def test_fabric_has_preprovisioned_switches(data_model, expected):
    assert _runner({}, data_model)._fabric_has_preprovisioned_switches() is expected


# --- _config_save matrix ---------------------------------------------------

def test_config_save_200_passes_through():
    # A successful config-save (no 'failed') is returned unchanged.
    result = {"changed": True, "response": {"RETURN_CODE": 200}}
    out = _runner(result, NON_PREPROV_DM)._config_save("inventory_config_save", {})
    assert not out.get("failed")
    assert out == result  # passed through unchanged (content, not identity)


def test_config_save_500_preprovisioned_is_non_fatal():
    result = {"failed": True, "msg": {"RETURN_CODE": 500, "MESSAGE": "Internal Server Error"}}
    runner = _runner(result, PREPROV_DM)
    with mock.patch.object(pipeline_base, "display") as disp:
        out = runner._config_save("inventory_config_save", {})
    assert out.get("failed") is False
    assert "non-fatal" in out.get("msg", "").lower()
    disp.warning.assert_called_once()


def test_config_save_500_non_preprovisioned_stays_fatal():
    # NEW row introduced by the gate: a 500 on a non-preprovisioned fabric is fatal.
    result = {"failed": True, "msg": {"RETURN_CODE": 500, "MESSAGE": "Internal Server Error"}}
    runner = _runner(result, NON_PREPROV_DM)
    with mock.patch.object(pipeline_base, "display") as disp:
        out = runner._config_save("inventory_config_save", {})
    assert out.get("failed") is True            # stays fatal
    assert out.get("msg") == result["msg"]      # response preserved for the caller
    disp.warning.assert_not_called()


def test_config_save_400_is_fatal():
    result = {"failed": True, "msg": {"RETURN_CODE": 400, "MESSAGE": "Bad Request"}}
    out = _runner(result, PREPROV_DM)._config_save("inventory_config_save", {})
    assert out.get("failed") is True


def test_config_save_malformed_msg_is_fatal():
    # 'msg' is not a dict -> RETURN_CODE lookup raises -> stays fatal even on preprov.
    result = {"failed": True, "msg": "boom, not a dict"}
    out = _runner(result, PREPROV_DM)._config_save("inventory_config_save", {})
    assert out.get("failed") is True


def test_config_save_missing_msg_is_fatal():
    result = {"failed": True}
    out = _runner(result, PREPROV_DM)._config_save("inventory_config_save", {})
    assert out.get("failed") is True
