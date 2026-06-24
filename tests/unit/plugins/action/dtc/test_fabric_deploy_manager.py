# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# MIT License (see the collection source for the full text).
#
# Unit tests for the config-save contract in fabric_deploy_manager.
# Covers issue #813 / PR #819: a non-200 config-save (e.g. HTTP 500) must
# surface as failed=True with the raw NDFC response INTACT (RETURN_CODE
# preserved), so pipeline_base._config_save can read RETURN_CODE and apply the
# non-fatal-on-500 policy. Uses only the Python stdlib (unittest.mock).
from __future__ import absolute_import, division, print_function

__metaclass__ = type

from unittest import mock

from ansible_collections.cisco.nac_dc_vxlan.plugins.action.dtc import (
    fabric_deploy_manager as fdm,
)


def _params(operation="config_save"):
    return {
        "fabric_name": "PREPROV1",
        "fabric_type": "VXLAN_EVPN",
        "operation": operation,
        "task_vars": {},
        "tmp": None,
        "action_module": mock.Mock(),
    }


def _run_config_save(send_request_response):
    """
    Drive ActionModule.manage_fabrics for operation='config_save' with the REST
    layer (_send_request) mocked to return the given response. Returns the
    mutated `results` dict that callers (pipeline_base) would receive.
    """
    results = {"failed": False, "changed": False}
    with mock.patch.object(fdm, "display") as disp, \
            mock.patch.object(
                fdm.FabricDeployManager, "_send_request",
                return_value=send_request_response):
        disp.columns = 80  # used in banner f-strings ('─' * display.columns)
        # manage_fabrics does not use `self` on the config_save path.
        fdm.ActionModule.manage_fabrics(mock.Mock(), results, _params())
    return results


def test_config_save_500_sets_failed_with_response_intact():
    resp = {
        "RETURN_CODE": 500,
        "METHOD": "POST",
        "MESSAGE": "Internal Server Error",
        "DATA": "Switch(es) are either reloading or not reachable ...",
    }
    results = _run_config_save(resp)
    assert results["failed"] is True
    # Response must be propagated intact so RETURN_CODE survives for the caller.
    assert results["msg"]["RETURN_CODE"] == 500
    assert "reloading or not reachable" in results["msg"]["DATA"]


def test_config_save_400_sets_failed_with_response_intact():
    resp = {"RETURN_CODE": 400, "METHOD": "POST", "MESSAGE": "Bad Request", "DATA": "nope"}
    results = _run_config_save(resp)
    assert results["failed"] is True
    assert results["msg"]["RETURN_CODE"] == 400  # non-500 code also preserved


def test_config_save_200_does_not_fail():
    resp = {"RETURN_CODE": 200, "METHOD": "POST", "MESSAGE": "OK", "DATA": "saved"}
    results = _run_config_save(resp)
    assert results["failed"] is False
