import pytest
import tarfile
import time

from assisted_service_client.rest import ApiException
from tests.base_test import BaseTest

class TestDownloadLogs(BaseTest):
    def setup_hosts(self, cluster_id, api_client, node_controller):
        '''setup nodes from ISO image and wait until they are registered'''
        # Generate and download cluster ISO
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        # Boot nodes into ISO
        node_controller.start_all_nodes()
        # Wait until hosts are discovered and update host roles
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
    
    def prepare_for_installation(self, cluster_id, api_client, node_controller):
        '''set roles and network params to prepare the cluster for install'''
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(cluster_id=cluster_id,
                                 api_client=api_client,
                                 controller=node_controller
                                 )

    def install_cluster_and_wait(self, cluster_id, api_client):
        '''start the cluster and wait for host to go to installing-in-progress state'''
        # Start cluster install
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # wait until all nodes are in Installed status, and the cluster moved to status installed
        self.wait_for_cluster_to_install(cluster_id=cluster_id, api_client=api_client)

    def test_collect_logs_on_success(self, api_client, node_controller, cluster):
        # Define new cluster and prepare it for installation
        cluster_id = cluster().id
        self.setup_hosts(cluster_id, api_client, node_controller)
        self.prepare_for_installation(cluster_id, api_client, node_controller)
        
        #download logs into a file. At this point logs are not uploaded
        path = "/tmp/test_on-success_logs.tar"
        self.verify_no_logs_uploaded(cluster_id, api_client, path)
        
        #install the cluster
        ts_start_at = time.time()
        self.install_cluster_and_wait(cluster_id, api_client)

        #download logs into a file. At this point logs exist
        expected_min_log_num = len(node_controller.list_nodes()) + 1
        self.verify_logs_uploaded(cluster_id, api_client, path, ts_start_at, expected_min_log_num)

    
    def test_collect_logs_on_failure(self, api_client, node_controller, cluster):
        '''cacnel insllation after at least one host is booted and check that logs are uploaded'''
        cluster_id = cluster().id
        self.generate_and_download_image(cluster_id=cluster_id, api_client=api_client)
        node_controller.start_all_nodes()
        self.wait_until_hosts_are_discovered(cluster_id=cluster_id, api_client=api_client)
        self.set_host_roles(cluster_id=cluster_id, api_client=api_client)
        self.set_network_params(
            cluster_id=cluster_id,
            api_client=api_client,
            controller=node_controller
        )

        ts_start_at = time.time()
        self.start_cluster_install(cluster_id=cluster_id, api_client=api_client)
        # Cancel cluster install once at least one host booted
        self.wait_for_one_host_to_boot_during_install(cluster_id=cluster_id, api_client=api_client)
        self.cancel_cluster_install(cluster_id=cluster_id, api_client=api_client)
        assert self.is_cluster_in_cancelled_status(
            cluster_id=cluster_id,
            api_client=api_client
        )
         #download logs into a file. At this point logs exist
        path = "/tmp/test_on_cancel_logs.tar"
        expected_min_log_num = 1 #at least the booted master has logs
        self.verify_logs_uploaded(cluster_id, api_client, path, ts_start_at, expected_min_log_num)

    def verify_no_logs_uploaded(self, cluster_id, api_client, path):
        with pytest.raises(ApiException) as ex:
            api_client.download_cluster_logs(cluster_id, path)

    def verify_logs_uploaded(self, cluster_id, api_client, path, ts_start_at, expected_min_log_num):
        api_client.download_cluster_logs(cluster_id, path)
        tar = tarfile.open(path)
        loglist = []
        for tarinfo in tar:
            loglist.append(tarinfo.name)
            assert tarinfo.mtime > ts_start_at
        tar.close()
        assert len(loglist) >= expected_min_log_num
