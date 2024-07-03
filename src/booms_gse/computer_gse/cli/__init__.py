import asyncio
from ipaddress import ip_address
from pathlib import Path

import click

from .. import network

SERIAL_LOG_PATH = Path(__file__).parent/'computer_serial.log'


class IPAddress(click.ParamType):
    name = 'IP address'
    """Restricts the type to a string for a valid IPv4 or IPv6 address."""
    def convert(self, value, param, ctx):
        try:
            ip = ip_address(value)
        except ValueError:
            self.fail('Invalid IP Address', param, ctx)

        return str(ip)


@click.group(chain=True)
@click.option('-a', '--address', default='0.0.0.0', type=IPAddress())
@click.option('-p', '--port', default='20501', type=click.IntRange(0, 65535))
@click.option('-f', '--from_file',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              path_type=Path))
@click.option('--debug', is_flag=True)
def gse(**kwargs):
    """Receive UDP datagrams and add to parsers"""
    # Setup logging


@gse.result_callback()
def process_pipeline(processors, address, port, from_file, debug):
    """Sets up the async run."""
    asyncio.run(network.receive_packets(address, port, processors, from_file))


@gse.command()
@click.argument('target_address', default='0.0.0.0', type=IPAddress())
@click.argument('target_port', default='20501', type=click.IntRange(0, 65535))
@click.option('--packet_id', help='Forward only this packet type.')
def forward(**kwargs):
    """Forward the UDP packets"""
    raise NotImplementedError('Serial forwarding is not implemented yet.')

    # async def forward_upd(address, port, from_file, target_kwargs=kwargs):
    #     await

    # return forward_upd


@gse.command()
@click.argument('packet_id')
@click.argument('target_serial', type=str)
def serial(packet_id, target_serial):
    """Pass the data from a selected device to a serial port"""
    raise NotImplementedError('Serial forwarding is not implemented yet.')


@gse.command()
def psuedoserial(address, port, from_file):
    """Pass networked BOOMS packets to pseudo-serial ports."""
    # log_file_handler = logging.FileHandler(SERIAL_LOG_PATH)
    # log_file_formatter = logging.Formatter(
    #     fmt='%(asctime)s - %(levelname)s - %(message)s')
    # log_file_handler.setFormatter(log_file_formatter)
    # network.logger.addHandler(log_file_handler)
    # network.logger.addHandler(logging.StreamHandler())
    # if kwargs['debug']:
    #     logging.basicConfig(level=logging.DEBUG)
    #     network.logger.setLevel(logging.DEBUG)

    return network.PacketPsuedoSerial()


@gse.command()
@click.argument('path',
                type=click.Path(file_okay=False,
                                writable=True,
                                path_type=Path))
def record(path):
    """Write networked BOOMS packets to files for each instrument."""
    # network.logger.addHandler(logging.StreamHandler())
    # if kwargs['debug']:
    #     network.logger.setLevel(logging.DEBUG)
    return network.PacketLogger(path)


if __name__ == '__main__':
    gse()
