# SPDX-License-Identifier: MIT
# Copyright (c) 2020 The Authors.

# Authors: Sherif Abdelwahab <@zasherif>
#          Phu Tran          <@phudtran>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:The above copyright
# notice and this permission notice shall be included in all copies or
# substantial portions of the Software.THE SOFTWARE IS PROVIDED "AS IS",
# WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
# TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
# FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging
import random
from kubernetes import client, config
from mizar.obj.endpoint import Endpoint
from mizar.obj.bouncer import Bouncer
from mizar.common.constants import *
from mizar.common.common import *
from mizar.store.operator_store import OprStore

logger = logging.getLogger()


class EndpointOperator(object):
    _instance = None

    def __new__(cls, **kwargs):
        if cls._instance is None:
            cls._instance = super(EndpointOperator, cls).__new__(cls)
            cls._init(cls, **kwargs)
        return cls._instance

    def _init(self, **kwargs):
        logger.info(kwargs)
        self.store = OprStore()
        config.load_incluster_config()
        self.obj_api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()

    def query_existing_endpoints(self):
        def list_endpoint_obj_fn(name, spec, plurals):
            logger.info("Bootstrapped {}".format(name))
            ep = Endpoint(name, self.obj_api, self.store, spec)
            if ep.status == OBJ_STATUS.ep_status_provisioned:
                self.store_update(ep)

        kube_list_obj(self.obj_api, RESOURCES.endpoints, list_endpoint_obj_fn)

    def get_endpoint_tmp_obj(self, name, spec):
        return Endpoint(name, self.obj_api, None, spec)

    def get_endpoint_stored_obj(self, name, spec):
        return Endpoint(name, self.obj_api, self.store, spec)

    def set_endpoint_provisioned(self, ep):
        ep.set_status(OBJ_STATUS.ep_status_provisioned)
        ep.update_obj()

    def store_update(self, ep):
        self.store.update_ep(ep)

    def store_delete(self, ep):
        self.store.delete_ep(ep.name)

    def on_endpoint_delete(self, body, spec, **kwargs):
        logger.info("on_endpoint_delete {}".format(spec))

    def on_endpoint_provisioned(self, body, spec, **kwargs):
        name = kwargs['name']
        logger.info("on_endpoint_provisioned {}".format(spec))
        ep = Endpoint(name, self.obj_api, self.store, spec)
        self.store.update_ep(ep)

    def update_bouncer_with_endpoints(self, bouncer):
        eps = self.store.get_eps_in_net(bouncer.net).values()
        bouncer.update_eps(eps)

    def update_endpoints_with_bouncers(self, bouncer):
        eps = self.store.get_eps_in_net(bouncer.net).values()
        for ep in eps:
            ep.update_bouncers(set([bouncer]))

    def create_scaled_endpoint(self, name, spec):
        logger.info("Create scaled endpoint {} spec {}".format(name, spec))
        ep = Endpoint(name, self.obj_api, self.store)
        ip = spec['clusterIP']
        # If not provided in Pod, use defaults
        # TODO: have it pod :)
        ep.set_vni(OBJ_DEFAULTS.default_vpc_vni)
        ep.set_vpc(OBJ_DEFAULTS.default_ep_vpc)
        ep.set_net(OBJ_DEFAULTS.default_ep_net)
        ep.set_ip(ip)
        ep.set_mac(self.rand_mac())
        ep.set_type(OBJ_DEFAULTS.ep_type_scaled)
        ep.set_status(OBJ_STATUS.ep_status_init)
        ep.create_obj()
        self.annotate_builtin_endpoints(name)

    def annotate_builtin_endpoints(self, name, namespace='default'):
        get_body = True
        while get_body:
            endpoint = self.core_api.read_namespaced_endpoints(
                name=name,
                namespace=namespace)
            endpoint.metadata.annotations[OBJ_DEFAULTS.mizar_service_annotation_key] = OBJ_DEFAULTS.mizar_service_annotation_val
            try:
                self.core_api.patch_namespaced_endpoints(
                    name=name,
                    namespace=namespace,
                    body=endpoint)
                get_body = False
            except:
                logger.debug(
                    "Retry updating annotating endpoints {}".format(name))
                get_body = True

    def delete_scaled_endpoint(self, ep):
        logger.info("Delete scaled endpoint {}".format(ep.name))
        ep.delete_obj()

    def rand_mac(self):
        return "a5:5b:00:%02x:%02x:%02x" % (
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )

    def update_scaled_endpoint_backend(self, name, spec):
        ep = self.store.get_ep(name)
        if ep is None:
            return None
        backends = set()
        for s in spec:
            for a in s['addresses']:
                backends.add(a['ip'])
        ep.set_backends(backends)
        self.store_update(ep)
        logger.info(
            "Update scaled endpoint {} with backends: {}".format(name, backends))
        return self.store.get_ep(name)

    def delete_endpoints_from_bouncers(self, bouncer):
        eps = self.store.get_eps_in_net(bouncer.net).values()
        bouncer.delete_eps(eps)

    def delete_bouncer_from_endpoints(self, bouncer):
        eps = self.store.get_eps_in_net(bouncer.net).values()
        for ep in eps:
            ep.update_bouncers(set([bouncer]), False)
