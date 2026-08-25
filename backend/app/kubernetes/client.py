from functools import lru_cache

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from app.config.settings import get_settings


class KubernetesConfigError(RuntimeError):
    pass


def load_kubernetes_config() -> None:
    mode = get_settings().kubernetes_mode

    if mode == "in-cluster":
        config.load_incluster_config()
        return

    if mode == "kubeconfig":
        config.load_kube_config()
        return

    if mode != "auto":
        raise KubernetesConfigError(f"Unsupported Kubernetes mode: {mode}")

    try:
        config.load_incluster_config()
    except ConfigException:
        try:
            config.load_kube_config()
        except ConfigException as exc:
            raise KubernetesConfigError("Unable to load Kubernetes configuration") from exc


@lru_cache
def get_core_v1_api() -> client.CoreV1Api:
    load_kubernetes_config()
    return client.CoreV1Api()


@lru_cache
def get_apps_v1_api() -> client.AppsV1Api:
    load_kubernetes_config()
    return client.AppsV1Api()


@lru_cache
def get_custom_objects_api() -> client.CustomObjectsApi:
    load_kubernetes_config()
    return client.CustomObjectsApi()


@lru_cache
def get_batch_v1_api() -> client.BatchV1Api:
    load_kubernetes_config()
    return client.BatchV1Api()


@lru_cache
def get_networking_v1_api() -> client.NetworkingV1Api:
    load_kubernetes_config()
    return client.NetworkingV1Api()


@lru_cache
def get_storage_v1_api() -> client.StorageV1Api:
    load_kubernetes_config()
    return client.StorageV1Api()
