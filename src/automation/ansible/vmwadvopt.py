#!/usr/bin/python
__author = 'asteer'

DOCUMENTATION = '''
'''

EXAMPLES = '''
- action : vmwadvopt host=172.17.100.120 user=root pwd=vmware dc=DataCenter cluster=Cluster option=Net.ReversePathFwdCheckPromisc value=1
'''


from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import atexit
import requests

requests.packages.urllib3.disable_warnings()


class VmwAdvOpt(object):
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
            self._cluster = self._find_cluster(self.module.params['cluster'])
            self._hosts = self._find_hosts()

    @property
    def ready(self):
        if not self._fault:
            if self.dc is not None and self.cluster is not None and len(self.hosts) > 0:
                return True
            elif self.dc is None:
                self._msg = "DataCenter not found"
            elif self.cluster is None:
                self._msg = "Cluster not found"
            elif not (len(self.hosts) > 0):
                self._msg = "No hosts found in cluster"
        return False

    @property
    def dc(self):
        return self._dc

    @property
    def cluster(self):
        return self._cluster

    @property
    def hosts(self):
        return self._hosts

    def _find_dc(self, dc_name=None):
        if dc_name is not None:
            for dc in self._rootFolder.childEntity:
                if dc.name == dc_name:
                    return dc
        return None

    def _find_cluster(self, cluster_name=None):
        if cluster_name is not None and self.dc is not None:
            for cluster in self.dc.hostFolder.childEntity:
                if cluster_name == cluster.name:
                    return cluster
        return None

    def _find_hosts(self):
        if self.cluster is not None:
            hosts = []
            for host in self.cluster.host:
                hosts.append(host)
            return hosts
        return None


def main():
    module = AnsibleModule(argument_spec = dict(
                                host=dict(required=True, type='str'),
                                user=dict(required=True, type='str'),
                                pwd=dict(required=True, type='str'),
                                cluster=dict(required=True, type='str'),
                                dc=dict(required=True, type='str', default=None),
                                option=dict(required=True, type='str'),
                                value=dict(required=True, type='str'),
                            ),
                           supports_check_mode=True)

    if module.params['option'].endswith('.'):
        module.fail_json(msg="Invalid option: subtree value replacement not supported")

    advopt = VmwAdvOpt(module)
    if not advopt.ready:
        module.fail_json(msg="Connection not ready: %s" % advopt._msg)

    result = {}
    result['changed'] = False

    hosts = advopt.hosts
    for h in hosts:
        opt = h.configManager.advancedOption.QueryOptions(name=module.params['option'])
        if str(opt[0].value) != module.params['value']:
            value = None
            #We have to mangle the types to match whats expected
            #Docs say anyType but barfs if not correct
            #Need to learn the dynamicTypeManager here?
            if type(opt[0].value) != type(module.params['value']):
                if type(opt[0].value).__name__ == 'long':
                    value = long(module.params['value'])
                elif type(opt[0].value).__name__ is 'int':
                    value = int(module.params['value'])
            else:
            #    #Should be a type str here
                value = module.params['value']

            opt[0].value = value
            result['changed'] = True

            if not module.check_mode:
                result[h.name] = 'changed'
                h.configManager.advancedOption.UpdateOptions(changedValue=opt)
            else:
                result[h.name] = 'would change'

        else:
            result[h.name] = 'no change'

    module.exit_json(**result)


def match_value_type(src, dest):
    # eg I need a <type 'long'> from a <type 'str>
    # Don't think I've got this option in Python2 (class hierarchy)
    new_dest = dest
    if not (type(src) == type(dest)):
        new_dest_type = type(type(src).__name__, (type(src),), ({}))
        new_dest = new_dest_type(dest)
    return new_dest


# import module snippets
from ansible.module_utils.basic import *
main()

