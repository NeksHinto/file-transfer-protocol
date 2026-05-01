#!/usr/bin/env python3

import os
import argparse
import shutil
import subprocess
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSController
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.cli import CLI


class SingleSwitchTopo(Topo):
    """Topología simple: un switch central, h1 (cliente) y h2 (servidor)."""

    def build(self, loss=10):
        # Hosts
        client = self.addHost("h1")
        server = self.addHost("h2")

        # Switch
        s1 = self.addSwitch("s1")

        # Links: pérdida solo en el enlace cliente->switch
        self.addLink(client, s1, cls=TCLink, loss=loss)
        self.addLink(server, s1, cls=TCLink)


def cleanup_mininet_state():
    """Remove leftover Mininet and testcontroller state before starting."""
    subprocess.run(["sudo", "pkill", "-f", "ovs-testcontroller"], check=False)
    subprocess.run(["sudo", "mn", "-c"], check=False)


def run(source_dir, loss):
    cleanup_mininet_state()

    topo = SingleSwitchTopo(loss=loss)
    net = Mininet(topo=topo, link=TCLink, controller=OVSController)
    net.start()

    print("\n*** Configurando directorio compartido...")
    shared_dir = "/tmp/tp1_shared"
    project_dir = "/TP1-Redes-2026"

    os.makedirs(shared_dir, exist_ok=True)
    for entry in os.listdir(shared_dir):
        entry_path = os.path.join(shared_dir, entry)
        if os.path.isdir(entry_path) and not os.path.islink(entry_path):
            shutil.rmtree(entry_path)
        else:
            os.unlink(entry_path)

    shutil.copytree(source_dir, shared_dir, dirs_exist_ok=True)

    for host in net.hosts:
        host.cmd(f"mkdir -p {project_dir}")
        host.cmd(f"mount --bind {shared_dir} {project_dir}")
        print(f"  Montado en {host.name}:{project_dir}")

    print(f"\n*** Pérdida de paquetes configurada: {loss}% en h1-s1")
    print(f"*** Directorio del proyecto disponible en: {project_dir}")
    print("*** Volcado de conexiones:")
    dumpNodeConnections(net.hosts)

    print("\n*** Probando conectividad:")
    net.pingAll()

    CLI(net)

    # Cleanup
    for host in net.hosts:
        host.cmd(f"umount {project_dir}")
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mininet TP1 Redes 2026")
    parser.add_argument(
        "--source-dir",
        type=str,
        default=os.path.expanduser("~/TP1-Redes-2026"),
        help="Ruta al directorio raíz del proyecto",
    )
    parser.add_argument(
        "--loss",
        type=int,
        default=10,
        help=(
            "Porcentaje de pérdida de paquetes en el enlace h1-s1 "
            "(default: 10)"
        ),
    )
    args = parser.parse_args()

    setLogLevel("info")
    run(args.source_dir, args.loss)
