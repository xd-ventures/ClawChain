"""GCP Compute Engine VM lifecycle management.

Uses Container-Optimized OS (COS) with a container declaration to run
PicoClaw as a Docker container. No custom base image needed.
"""

import logging

log = logging.getLogger("orchestrator.gcp")

# COS image — always use the latest stable Container-Optimized OS
COS_IMAGE_PROJECT = "cos-cloud"
COS_IMAGE_FAMILY = "cos-stable"


class GCPManager:
    def __init__(
        self,
        project_id: str,
        zone: str,
        machine_type: str,
        network: str = "default",
        service_account_email: str = "",
    ):
        self.project = project_id
        self.zone = zone
        self.machine_type = f"zones/{zone}/machineTypes/{machine_type}"
        self.network = f"global/networks/{network}"
        self.sa_email = service_account_email
        from google.cloud import compute_v1
        self._compute_v1 = compute_v1
        self.client = compute_v1.InstancesClient()
        self.images_client = compute_v1.ImagesClient()

    def _get_cos_image(self) -> str:
        """Get the latest COS stable image self-link."""
        image = self.images_client.get_from_family(
            project=COS_IMAGE_PROJECT, family=COS_IMAGE_FAMILY
        )
        return image.self_link

    def create_instance(
        self,
        instance_name: str,
        cloud_init_userdata: str,
        container_declaration: str,
    ) -> str:
        """Create a COS VM that runs a PicoClaw container.

        Args:
            instance_name: GCP instance name
            cloud_init_userdata: cloud-init YAML that writes config to host
            container_declaration: gce-container-declaration YAML for the container spec
        """
        cv1 = self._compute_v1
        cos_image = self._get_cos_image()

        disk = cv1.AttachedDisk(
            auto_delete=True,
            boot=True,
            initialize_params=cv1.AttachedDiskInitializeParams(
                source_image=cos_image,
                disk_size_gb=10,
            ),
        )

        access_config = cv1.AccessConfig(
            name="External NAT",
            type_="ONE_TO_ONE_NAT",
        )
        network_interface = cv1.NetworkInterface(
            network=self.network,
            access_configs=[access_config],
        )

        metadata = cv1.Metadata(
            items=[
                cv1.Items(key="user-data", value=cloud_init_userdata),
                cv1.Items(key="gce-container-declaration", value=container_declaration),
            ]
        )

        instance = cv1.Instance(
            name=instance_name,
            machine_type=self.machine_type,
            disks=[disk],
            network_interfaces=[network_interface],
            metadata=metadata,
        )

        if self.sa_email:
            instance.service_accounts = [
                cv1.ServiceAccount(
                    email=self.sa_email,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            ]

        op = self.client.insert(project=self.project, zone=self.zone, instance_resource=instance)
        log.info(f"VM create operation started: {instance_name}")
        return op.name

    def delete_instance(self, instance_name: str) -> str:
        """Delete a VM."""
        op = self.client.delete(project=self.project, zone=self.zone, instance=instance_name)
        log.info(f"VM delete operation started: {instance_name}")
        return op.name

    def get_instance_status(self, instance_name: str) -> str | None:
        """Get instance status (RUNNING, STAGING, TERMINATED, etc). Returns None if not found."""
        try:
            instance = self.client.get(project=self.project, zone=self.zone, instance=instance_name)
            return instance.status
        except Exception:
            return None

    def get_instance_ip(self, instance_name: str) -> str | None:
        """Get the external IP of a running instance."""
        try:
            instance = self.client.get(project=self.project, zone=self.zone, instance=instance_name)
            for iface in instance.network_interfaces:
                for ac in iface.access_configs:
                    if ac.nat_i_p:
                        return ac.nat_i_p
            return None
        except Exception:
            return None
