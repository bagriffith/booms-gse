import asyncio
from pathlib import Path
from ipaddress import ip_address
import logging
import asyncio
import click
from flight_computer import network

SERIAL_LOG_PATH = Path(__file__).parent/'computer_serial.log'


class IPAddress(click.ParamType):
    def convert(self, value, param, ctx):
        try:
            ip = ip_address(value)
        except ValueError:
            self.fail('Invalid IP Address', param, ctx)

        return str(ip)


@click.group()
def cli():
    pass


@cli.command()
@click.option('-a', '--address', default='0.0.0.0', type=IPAddress())
@click.option('-p', '--port', default='20501', type=click.IntRange(0, 65535))
@click.option('-f', '--from_file', default=None,
              help='Source file to playback.',
              type=click.Path(file_okay=True, dir_okay=False,
                              readable=True, path_type=Path))
@click.option('--debug', is_flag=True)
@click.option('-s', '--source', help="Flight computer data file to use.")
def serial(address, port, from_file, **kwargs):
    """Pass networked BOOMS packets to pseudo-serial ports."""
    log_file_handler = logging.FileHandler(SERIAL_LOG_PATH)
    log_file_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s')
    log_file_handler.setFormatter(log_file_formatter)
    network.logger.addHandler(log_file_handler)
    network.logger.addHandler(logging.StreamHandler())
    if kwargs['debug']:
        logging.basicConfig(level=logging.DEBUG)
        network.logger.setLevel(logging.DEBUG)

    asyncio.run(network.run_serial(address, port,
                                   from_file=from_file),
                debug=kwargs['debug'])


@cli.command()
@click.argument('path',
                type=click.Path(file_okay=False,
                                writable=True,
                                path_type=Path))
@click.option('-a', '--address', default='0.0.0.0', type=IPAddress())
@click.option('-p', '--port', default='20501', type=click.IntRange(0, 65535))
@click.option('-f', '--from_file', default=None,
              help='Source file to playback.',
              type=click.Path(file_okay=True, dir_okay=False,
                              readable=True, path_type=Path))
@click.option('--debug', is_flag=True)
@click.option('-f', '--from', help='Source file to playback.',
              type=click.Path(file_okay=True, dir_okay=False,
                              readable=True, path_type=Path))
def record(path, address, port, from_file, **kwargs):
    """Write networked BOOMS packets to files for each instrument."""
    network.logger.addHandler(logging.StreamHandler())
    if kwargs['debug']:
        network.logger.setLevel(logging.DEBUG)

    asyncio.run(network.run_file_logger(path, address, port,
                                        from_file=from_file))


if __name__ == '__main__':
    cli()
