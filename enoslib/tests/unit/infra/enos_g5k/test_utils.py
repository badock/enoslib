import copy
from enoslib.infra.enos_g5k import utils
from enoslib.infra.enos_g5k.error import (MissingNetworkError,
                                         NotEnoughNodesError)
from enoslib.infra.enos_g5k.schema import KAVLAN, PROD
from enoslib.tests.unit import EnosTest
from execo import Host
import execo_g5k as ex5
from execo_g5k import api_utils as api
import mock


# TODO(msimonin): use patch
class TestMountNics(EnosTest):

    def setUp(self):
        self.c_resources = {
            "machines":[{
                "primary_network": "network_1",
                "cluster": "foo"
            }],
            "networks":[{
                "id": "network_1",
                "roles": ["n1", "n2"]
            }]
        }

    @mock.patch("enoslib.infra.enos_g5k.utils._mount_secondary_nics")
    @mock.patch("enoslib.infra.enos_g5k.utils.get_cluster_interfaces", return_value=[("eth0", "en0")])
    def test_primary(self, mock__mount_secondary_nics, mock_get_cluster_interfaces):
        utils.mount_nics(self.c_resources)
        self.assertCountEqual([("en0", ["n1", "n2"])], self.c_resources["machines"][0]["_c_nics"])


class TestMountSecondaryNics(EnosTest):

    def test_exact(self):
        desc = {
            "cluster": "foocluster",
            "_c_nodes": ["foocluster-1", "foocluster-2"],
            "secondary_networks": ["network_1", "network_2"]
        }
        networks = [
            {
                "type": KAVLAN,
                "id": "network_1",
                "role": "net_role_1",
                "site": "rennes",
                "_c_network": {"vlan_id": 4, "site": "rennes"}
            },
            {
                "type": KAVLAN,
                "id": "network_2",
                "roles": ["net_role_2", "net_role_3"],
                "site": "rennes",
                "_c_network": {"vlan_id": 5, "site": "rennes"}},
        ]
        utils.get_cluster_interfaces = mock.MagicMock(return_value=[("eth0", "en0"), ("eth1", "en1")])
        ex5.get_cluster_site = mock.MagicMock(return_value="rennes")
        api.set_nodes_vlan = mock.MagicMock()
        utils._mount_secondary_nics(desc, networks)
        self.assertCountEqual([("en0", ["net_role_1"]), ("en1", ["net_role_2", "net_role_3"])], desc["_c_nics"])


class TestConcretizeNetwork(EnosTest):

    def setUp(self):
        self.resources = {
            "networks":[{
                "type": KAVLAN,
                "site": "rennes",
                "id": "role1"
            }, {
                "type": KAVLAN,
                "site": "rennes",
                "id": "role2"
            }]
        }
        ex5.get_resource_attributes = mock.MagicMock(return_value={'kavlans': {'default': {},'4': {}, '5': {}}})

    def test_act(self):
        networks = [
            { "site": "rennes", "vlan_id": 4},
            { "site": "rennes", "vlan_id": 5}
        ]
        utils.concretize_networks(self.resources, networks)
        self.assertEquals(networks[0], self.resources["networks"][0]["_c_network"])
        self.assertEquals(networks[1], self.resources["networks"][1]["_c_network"])

    def test_prod(self):
        self.resources["networks"][0]["type"] = PROD
        networks = [
            { "site": "rennes", "vlan_id": 5}
        ]
        utils.concretize_networks(self.resources, networks)
        # self.assertEquals(networks[0], self.resources["networks"][0]["_c_network"])
        self.assertEquals(None, self.resources["networks"][0]["_c_network"]["vlan_id"])
        self.assertEquals(networks[0], self.resources["networks"][1]["_c_network"])

    def test_one_missing(self):
        networks = [
            { "site": "rennes", "vlan_id": 4},
        ]
        with self.assertRaises(MissingNetworkError):
            utils.concretize_networks(self.resources, networks)

    def test_not_order_dependent(self):
        networks_1 = [
            { "site": "rennes", "vlan_id": 4},
            { "site": "rennes", "vlan_id": 5}
        ]
        networks_2 = [
            { "site": "rennes", "vlan_id": 5},
            { "site": "rennes", "vlan_id": 4}
        ]
        resources_1 = copy.deepcopy(self.resources)
        resources_2 = copy.deepcopy(self.resources)
        utils.concretize_networks(resources_1, networks_1)
        utils.concretize_networks(resources_2, networks_2)
        self.assertCountEqual(resources_1["networks"], resources_2["networks"])


class TestConcretizeNodes(EnosTest):

    def setUp(self):
        self.resources = {
            "machines": [{
                "role": "compute",
                "nodes": 1,
                "cluster": "foocluster",
            }, {
                "role": "compute",
                "nodes": 1,
                "cluster": "barcluster",
            }],
        }

    def test_exact(self):
        nodes = [Host("foocluster-1"), Host("barcluster-2")]
        utils.concretize_nodes(self.resources, nodes)
        self.assertCountEqual(self.resources["machines"][0]["_c_nodes"],
                              ["foocluster-1"])
        self.assertCountEqual(self.resources["machines"][1]["_c_nodes"],
                              ["barcluster-2"])

    def test_one_missing(self):
        nodes = [Host("foocluster-1")]
        utils.concretize_nodes(self.resources, nodes)
        self.assertCountEqual(self.resources["machines"][0]["_c_nodes"],
                              ["foocluster-1"])
        self.assertCountEqual(self.resources["machines"][1]["_c_nodes"], [])


    def test_same_cluster(self):
        nodes = [Host("foocluster-1"), Host("foocluster-2")]
        self.resources["machines"][1]["cluster"] = "foocluster"
        utils.concretize_nodes(self.resources, nodes)
        self.assertCountEqual(self.resources["machines"][0]["_c_nodes"],
                              ["foocluster-1"])
        self.assertCountEqual(self.resources["machines"][1]["_c_nodes"], ["foocluster-2"])

    def test_not_order_dependent(self):
        nodes = [Host("foocluster-1"), Host("foocluster-2"), Host("foocluster-3")]
        self.resources["machines"][0]["nodes"] = 2
        resources_1 = copy.deepcopy(self.resources)
        utils.concretize_nodes(resources_1, nodes)
        nodes = [Host("foocluster-2"), Host("foocluster-3"), Host("foocluster-1")]
        resources_2 = copy.deepcopy(self.resources)
        resources_2["machines"][0]["nodes"] = 2
        utils.concretize_nodes(resources_2, nodes)

        self.assertCountEqual(resources_1["machines"][0]["_c_nodes"],
                              resources_2["machines"][0]["_c_nodes"])



class TestConcretizeNodesMin(EnosTest):

    def setUp(self):
        self.resources = {
            "machines": [{
                "role": "compute",
                "nodes": 1,
                "cluster": "foocluster",
            }, {
                "role": "compute",
                "nodes": 1,
                "cluster": "foocluster",
                "min": 1
            }],
        }

    def test_exact(self):
        nodes = [Host("foocluster-1"), Host("foocluster-2")]
        utils.concretize_nodes(self.resources, nodes)
        self.assertCountEqual(self.resources["machines"][0]["_c_nodes"],
                              ["foocluster-2"])
        # Description with min are filled first
        self.assertCountEqual(self.resources["machines"][1]["_c_nodes"],
                              ["foocluster-1"])

    def test_one_missing(self):
        nodes = [Host("foocluster-1")]
        utils.concretize_nodes(self.resources, nodes)
        self.assertCountEqual(self.resources["machines"][0]["_c_nodes"], [])
        self.assertCountEqual(self.resources["machines"][1]["_c_nodes"], ["foocluster-1"])

    def test_all_missing(self):
        nodes = []
        with self.assertRaises(NotEnoughNodesError):
            utils.concretize_nodes(self.resources, nodes)

