#!/usr/bin/python
__author = 'asteer'

DOCUMENTATION = '''
'''

EXAMPLES = '''
- action : vmwpromisc host=172.17.100.120 user=root pwd=vmware dc=DataCenter network=DVPortGroup state=set
'''


from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import atexit
import requests
import time

requests.packages.urllib3.disable_warnings()


class VmwPromisc(object):
    def __init__(self, module):
        self.module = module
        self.auth = {}
        self.auth['host'] = module.params['host']
        self.auth['user'] = module.params['user']
        self.auth['pwd'] = module.params['pwd']
        self._si = None
        self._msg = ''
        self._fault = False

        try:
            self._si = SmartConnect(**self.auth)
        except Exception as e:
            self._fault = True
            self._msg = 'Error connecting or authenticating'

        if self._si is not None:
            atexit.register(Disconnect, self._si)

            self._content = self._si.RetrieveContent() or None
            self._rootFolder = self._content.rootFolder or None

            self._dc = self._find_dc(self.module.params['dc'])
            self._network = self._find_network(self.module.params['network'])

    @property
    def ready(self):
        if not self._fault:
            if self.dc is not None and self.network is not None:
                return True
            elif self.dc is None:
                self._msg = "DataCenter not found"
            elif self.network is None:
                self._msg = "Network not found"
        return False

    @property
    def dc(self):
        return self._dc

    @property
    def network(self):
        return self._network

    def _find_dc(self, dc_name=None):
        if dc_name is not None:
            for dc in self._rootFolder.childEntity:
                if dc.name == dc_name:
                    return dc
        return None

    def _find_network(self, network_name=None):
        if network_name is not None and self.dc is not None:
            for network in self.dc.networkFolder.childEntity:
                if network_name == network.name:
                    return network
        return None


def main():
    module = AnsibleModule(argument_spec = dict(
                                host=dict(required=True, type='str'),
                                user=dict(required=True, type='str'),
                                pwd=dict(required=True, type='str'),
                                network=dict(required=True, type='str'),
                                dc=dict(required=True, type='str', default=None),
                                state=dict(default='set', choices=['set', 'unset'], type='str'),
                            ),
                           supports_check_mode=True)

    promisc = VmwPromisc(module)
    if not promisc.ready:
        module.fail_json(msg="Connection not ready: %s" % promisc._msg)

    result = {}
    result['changed'] = False

    if type(promisc.network) is vim.dvs.DistributedVirtualPortgroup:
        promisc_mode = promisc.network.config.defaultPortConfig.securityPolicy.allowPromiscuous.value
        forged_mode = promisc.network.config.defaultPortConfig.securityPolicy.forgedTransmits.value

        config_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
        config_spec.defaultPortConfig = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
        config_spec.defaultPortConfig.securityPolicy = vim.dvs.VmwareDistributedVirtualSwitch.SecurityPolicy()
        policy = config_spec.defaultPortConfig.securityPolicy

        if module.params['state'] == 'set':
            if promisc_mode is False:
                result['changed'] = True
                result['allowPromiscuous'] = True
                policy.allowPromiscuous = vim.BoolPolicy(value=True)
            if forged_mode is False:
                result['changed'] = True
                result['forgedTransmits'] = True
                policy.forgedTransmits = vim.BoolPolicy(value=True)
        else:
            if promisc_mode is True:
                result['changed'] = True
                result['allowPromiscuous'] = False
                policy.allowPromiscuous = vim.BoolPolicy(value=False)
            if forged_mode is True:
                result['changed'] = True
                result['forgedTransmits'] = False
                policy.forgedTransmits = vim.BoolPolicy(value=False)

        if not module.check_mode and result['changed']:
            config_spec.configVersion = promisc.network.config.configVersion
            task = promisc.network.ReconfigureDVPortgroup_Task(config_spec)
            while task.info.state == 'running':
                # OK, this is just nasty
                time.sleep(1)
            result['task_state'] = task.info.state

    else:
        module.fail_json('Selected network is not of type vim.dvs.DistributedVirtualPortgroup')

    module.exit_json(**result)


# import module snippets
from ansible.module_utils.basic import *
main()

